#include <functional>
#include <memory>
#include <optional>
#include <queue>
#include <type_traits>
#include "tx_api.h"

class ThreadDispatcher {
    std::queue<std::function<void()>> m_queue;
    TX_MUTEX m_queue_mutex;
    TX_SEMAPHORE m_jobs_available;

public:
    ThreadDispatcher() {
        // Mutex to protect the std::queue from concurrent memory access.
        // TX_INHERIT helps prevent priority inversion in RTOS environments.
        tx_mutex_create(&m_queue_mutex, (CHAR*)"q_mut", TX_INHERIT);
        
        // Counting semaphore to track the number of jobs in the queue
        tx_semaphore_create(&m_jobs_available, (CHAR*)"jobs", 0);
    }

    ~ThreadDispatcher() {
        tx_mutex_delete(&m_queue_mutex);
        tx_semaphore_delete(&m_jobs_available);
    }

    // --------------------------------------------------------
    // RUN BY THE TARGET THREAD
    // --------------------------------------------------------
    void run_loop() {
        while (true) {
            // 1. Sleep until the semaphore count is > 0 (meaning a job is in the queue)
            tx_semaphore_get(&m_jobs_available, TX_WAIT_FOREVER);

            std::function<void()> current_job;

            // 2. Lock the queue to safely extract the next job
            tx_mutex_get(&m_queue_mutex, TX_WAIT_FOREVER);
            if (!m_queue.empty()) {
                // Use std::move to prevent copying the heavy std::function
                current_job = std::move(m_queue.front());
                m_queue.pop();
            }
            tx_mutex_put(&m_queue_mutex);

            // 3. Execute the job OUTSIDE the mutex lock!
            // This ensures other threads can keep queuing new jobs while this one runs.
            if (current_job) {
                current_job();
            }
        }
    }

    // --------------------------------------------------------
    // RUN BY ANY CALLING THREAD
    // --------------------------------------------------------
    template <typename F>
    auto dispatch(F&& func) {
        using ActualReturn = std::invoke_result_t<F>;
        using StoredReturn = std::conditional_t<std::is_void_v<ActualReturn>, bool, ActualReturn>;

        struct JobState {
            std::optional<StoredReturn> result;
            TX_SEMAPHORE done_sem;

            JobState() { tx_semaphore_create(&done_sem, (CHAR*)"done", 0); }
            ~JobState() { tx_semaphore_delete(&done_sem); }
        };

        auto state = std::make_shared<JobState>();

        // 1. Wrap the function and state
        auto job = [f = std::forward<F>(func), state]() mutable {
            if constexpr (std::is_void_v<ActualReturn>) {
                f();
                state->result = true; 
            } else {
                state->result = f();
            }
            tx_semaphore_put(&state->done_sem);
        };

        // 2. Lock the queue and push the new job
        tx_mutex_get(&m_queue_mutex, TX_WAIT_FOREVER);
        m_queue.push(std::move(job));
        tx_mutex_put(&m_queue_mutex);

        // 3. Increment the counting semaphore to wake up the target thread
        tx_semaphore_put(&m_jobs_available);

        // 4. Return the waitable lambda
        return [state]() -> ActualReturn {
            tx_semaphore_get(&state->done_sem, TX_WAIT_FOREVER);
            if constexpr (!std::is_void_v<ActualReturn>) {
                return *(state->result);
            }
        };
    }
};

#include <open62541/types.h>
#include <string>
#include <vector>
#include <map>

// 1. Define what a reference is (The Edge in the graph)
struct OpcReference {
    UA_NodeId targetNodeId;
    UA_NodeId referenceTypeId; // e.g., HasComponent, HasProperty
    bool isForward;            // True if this node points TO the target
};

// 2. Define the Node (The Vertex in the graph)
struct OpcNode {
    UA_NodeId nodeId;
    std::string browseName;
    std::string displayName;
    UA_NodeClass nodeClass;
    
    // Instead of holding nested nodes, we just hold the IDs!
    std::vector<OpcReference> references; 
};

// 3. Re-use the Comparator from our previous recursive script
struct NodeIdCompare {
    bool operator()(const UA_NodeId& lhs, const UA_NodeId& rhs) const noexcept {
        return UA_NodeId_order(&lhs, &rhs) == UA_ORDER_LESS;
    }
};

// 4. The actual Data Structure
using OpcAddressSpace = std::map<UA_NodeId, OpcNode, NodeIdCompare>;









#include <open62541/client_config_default.h>
#include <open62541/client_highlevel.h>

#include <iostream>
#include <map>
#include <memory>
#include <string>
#include <vector>

// ---------------------------------------------------------
// 1. Memory-Safe NodeId Wrapper (For the Map Key)
// ---------------------------------------------------------
class SafeNodeId {
    UA_NodeId m_id;
public:
    // Constructor: Deep copy from a raw C struct
    explicit SafeNodeId(const UA_NodeId& src) {
        UA_NodeId_init(&m_id);
        UA_NodeId_copy(&src, &m_id);
    }
    
    // Copy Constructor
    SafeNodeId(const SafeNodeId& other) {
        UA_NodeId_init(&m_id);
        UA_NodeId_copy(&other.m_id, &m_id);
    }

    ~SafeNodeId() { UA_NodeId_clear(&m_id); }

    const UA_NodeId& get() const { return m_id; }

    // Required by std::map to sort the keys!
    bool operator<(const SafeNodeId& rhs) const {
        return UA_NodeId_order(&m_id, &rhs.get()) == UA_ORDER_LESS;
    }
};

// ---------------------------------------------------------
// 2. Safe C++ Graph Data Structures (The Map Values)
// ---------------------------------------------------------
struct OpcReference {
    SafeNodeId targetId;
    std::string browseName; 
    UA_NodeClass targetNodeClass;
};

struct OpcNode {
    SafeNodeId nodeId; // Keep a copy of own ID for convenience
    std::vector<OpcReference> references;
};

using OpcAddressSpace = std::map<SafeNodeId, OpcNode>;

// ---------------------------------------------------------
// 3. RAII Helpers
// ---------------------------------------------------------
struct BrowseResponseGuard {
    UA_BrowseResponse response;
    explicit BrowseResponseGuard(UA_BrowseResponse resp) : response(resp) {}
    ~BrowseResponseGuard() { UA_BrowseResponse_clear(&response); }
};

std::string to_cpp_string(const UA_String& ua_str) {
    if (!ua_str.data || ua_str.length == 0) return "";
    return std::string(reinterpret_cast<const char*>(ua_str.data), ua_str.length);
}

// ---------------------------------------------------------
// 4. The Recursive Graph Builder
// ---------------------------------------------------------
void build_address_space(UA_Client* client, const UA_NodeId& currentNode, OpcAddressSpace& addressSpace) 
{
    SafeNodeId safeCurrentId(currentNode);

    // CYCLE PREVENTION: 
    // If the node is already a key in our map, we have already browsed it!
    // Stop recursion immediately to prevent infinite loops.
    if (addressSpace.find(safeCurrentId) != addressSpace.end()) {
        return;
    }

    // Insert the node into the map FIRST. 
    // This marks it as "visited" before we even start checking its children.
    OpcNode newNode;
    newNode.nodeId = safeCurrentId;
    addressSpace[safeCurrentId] = newNode;

    // Build the Browse Request
    UA_BrowseRequest bReq;
    UA_BrowseRequest_init(&bReq);
    bReq.requestedMaxReferencesPerNode = 0;
    bReq.nodesToBrowseSize = 1;

    UA_BrowseDescription bDesc;
    UA_BrowseDescription_init(&bDesc);
    bDesc.nodeId = currentNode;
    bDesc.resultMask = UA_BROWSERESULTMASK_ALL;
    bDesc.referenceTypeId = UA_NODEID_NUMERIC(0, UA_NS0ID_HIERARCHICALREFERENCES);
    bDesc.browseDirection = UA_BROWSEDIRECTION_FORWARD;
    bDesc.includeSubtypes = true;

    bReq.nodesToBrowse = &bDesc;

    // Execute Browse safely
    BrowseResponseGuard browseGuard(UA_Client_Service_browse(client, bReq));
    const UA_BrowseResponse& bResp = browseGuard.response;

    if (bResp.responseHeader.serviceResult != UA_STATUSCODE_GOOD || bResp.resultsSize == 0) {
        return;
    }

    const UA_BrowseResult& result = bResp.results[0];
    if (result.statusCode != UA_STATUSCODE_GOOD) {
        return;
    }

    // Iterate through children
    for (size_t i = 0; i < result.referencesSize; ++i) {
        const UA_ReferenceDescription* ref = &result.references[i];
        
        // 1. Extract the raw C data into our safe C++ reference struct
        OpcReference safeRef {
            SafeNodeId(ref->nodeId.nodeId), // Deep copy the child's ID
            to_cpp_string(ref->browseName.name), // Deep copy the string
            ref->nodeClass
        };

        // 2. Add the edge to our current node in the map
        addressSpace[safeCurrentId].references.push_back(safeRef);

        // 3. Recurse deeper into the graph using the child's ID!
        build_address_space(client, ref->nodeId.nodeId, addressSpace);
    }
}




void print_address_space_tree(const OpcAddressSpace& addressSpace, 
                              const SafeNodeId& currentNodeId, 
                              const std::string& currentName, 
                              int depth, 
                              std::set<SafeNodeId>& printed_nodes) 
{
    std::string indent(depth * 3, ' ');

    // 1. Check if the node actually exists in our map
    auto it = addressSpace.find(currentNodeId);
    if (it == addressSpace.end()) {
        std::cout << indent << "- " << currentName << " [Node details not browsed]\n";
        return;
    }

    // 2. CYCLE PREVENTION: Have we already printed this node's children?
    if (printed_nodes.find(currentNodeId) != printed_nodes.end()) {
        std::cout << indent << "- " << currentName 
                  << " [-> Link to already printed node: " 
                  << nodeid_to_string(currentNodeId) << "]\n";
        return;
    }

    // Mark this node as printed so we don't recurse into it again
    printed_nodes.insert(currentNodeId);

    // 3. Print the current node
    std::cout << indent << "- " << currentName 
              << " (" << nodeid_to_string(currentNodeId) << ")\n";

    // 4. Iterate through its references and recurse!
    const OpcNode& nodeData = it->second;
    for (const OpcReference& ref : nodeData.references) {
        print_address_space_tree(addressSpace, 
                                 ref.targetId, 
                                 ref.browseName, 
                                 depth + 1, 
                                 printed_nodes);
    }
}
