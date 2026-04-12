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



std::string nodeid_to_string(const SafeNodeId& id) {
    UA_String out = UA_STRING_NULL;
    UA_NodeId_print(&id.get(), &out);
    
    std::string result;
    if (out.data) {
        result = std::string(reinterpret_cast<const char*>(out.data), out.length);
        UA_String_clear(&out); // Free the memory allocated by UA_NodeId_print
    }
    return result;
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













#include <open62541/client_highlevel.h>
#include <concepts>
#include <optional>
#include <string>

// 1. C++20 Concept to restrict to types we know how to handle
template <typename T>
concept OpcScalar = std::is_same_v<T, bool> ||
                    std::is_same_v<T, int32_t> ||
                    std::is_same_v<T, uint32_t> ||
                    std::is_same_v<T, float> ||
                    std::is_same_v<T, double> ||
                    std::is_same_v<T, std::string>;

// 2. Type matching helper
template <OpcScalar T>
constexpr const UA_DataType* get_ua_type() {
    if constexpr (std::is_same_v<T, bool>)     return &UA_TYPES;
    if constexpr (std::is_same_v<T, int32_t>)  return &UA_TYPES;
    if constexpr (std::is_same_v<T, uint32_t>) return &UA_TYPES;
    if constexpr (std::is_same_v<T, float>)    return &UA_TYPES;
    if constexpr (std::is_same_v<T, double>)   return &UA_TYPES;
    if constexpr (std::is_same_v<T, std::string>) return &UA_TYPES;
}

// ---------------------------------------------------------
// WRITE NODE
// ---------------------------------------------------------
template <OpcScalar T>
UA_StatusCode write_node(UA_Client* client, const UA_NodeId& nodeId, const T& value) {
    UA_Variant variant;
    UA_Variant_init(&variant);

    if constexpr (std::is_same_v<T, std::string>) {
        // Strings require specific conversion
        UA_String ua_str = UA_String_fromChars(value.c_str());
        // setScalar takes ownership of the memory, no need to copy again
        UA_Variant_setScalar(&variant, &ua_str, &UA_TYPES);
    } else {
        // Numeric types can just be deeply copied in
        UA_Variant_setScalarCopy(&variant, &value, get_ua_type<T>());
    }

    // Execute the write
    UA_StatusCode status = UA_Client_writeValueAttribute(client, nodeId, &variant);

    // Free the variant's internal memory immediately
    UA_Variant_clear(&variant);
    
    return status;
}

// ---------------------------------------------------------
// READ NODE
// ---------------------------------------------------------
template <OpcScalar T>
std::optional<T> read_node(UA_Client* client, const UA_NodeId& nodeId) {
    UA_Variant variant;
    UA_Variant_init(&variant);

    UA_StatusCode status = UA_Client_readValueAttribute(client, nodeId, &variant);

    if (status != UA_STATUSCODE_GOOD) {
        UA_Variant_clear(&variant);
        return std::nullopt; // Safely return nothing on network/node error
    }

    // Check if the server actually returned the type we expected
    if (variant.type != get_ua_type<T>() || !UA_Variant_isScalar(&variant)) {
        UA_Variant_clear(&variant);
        return std::nullopt; // Type mismatch
    }

    std::optional<T> result;

    if constexpr (std::is_same_v<T, std::string>) {
        // Extract the C-string into a safe C++ string
        UA_String* ua_str = static_cast<UA_String*>(variant.data);
        if (ua_str->data && ua_str->length > 0) {
            result = std::string(reinterpret_cast<const char*>(ua_str->data), ua_str->length);
        } else {
            result = std::string("");
        }
    } else {
        // Extract numeric types directly
        result = *static_cast<T*>(variant.data);
    }

    // Free the dynamic memory the server allocated for the variant
    UA_Variant_clear(&variant);

    return result;
}

#include <open62541/client_highlevel.h>
#include <open62541/client_subscriptions.h>
#include <functional>
#include <iostream>

// 1. The Wrapper that lives on the heap
template <OpcScalar T>
struct MonitoredItemContext {
    std::function<void(const T&)> callback;
};

// 2. The Static Data Change Callback (Matches open62541 C-signature)
template <OpcScalar T>
static void data_change_callback(UA_Client *client, UA_UInt32 subId, void *subContext,
                                 UA_UInt32 monId, void *monContext, UA_DataValue *value) 
{
    // If there is no value or data is invalid, ignore it
    if (!value || !value->hasValue || !monContext) return;

    // Cast the void* back to our C++ struct
    auto* ctx = static_cast<MonitoredItemContext<T>*>(monContext);

    // Verify the server sent the type we actually expect
    if (value->value.type != get_ua_type<T>() || !UA_Variant_isScalar(&value->value)) {
        return; 
    }

    // Extract the data and invoke the user's C++ lambda!
    if constexpr (std::is_same_v<T, std::string>) {
        UA_String* ua_str = static_cast<UA_String*>(value->value.data);
        if (ua_str->data && ua_str->length > 0) {
            ctx->callback(std::string(reinterpret_cast<const char*>(ua_str->data), ua_str->length));
        } else {
            ctx->callback(std::string(""));
        }
    } else {
        ctx->callback(*static_cast<T*>(value->value.data));
    }
}

// 3. The Static Delete Callback (Crucial for preventing memory leaks)
template <OpcScalar T>
static void delete_monitored_item_callback(UA_Client *client, UA_UInt32 subId, void *subContext,
                                           UA_UInt32 monId, void *monContext) 
{
    if (monContext) {
        auto* ctx = static_cast<MonitoredItemContext<T>*>(monContext);
        delete ctx; // Safely free the heap memory containing the std::function
    }
}


template <OpcScalar T>
UA_UInt32 subscribe_to_node(UA_Client* client, 
                            UA_UInt32 subscriptionId, 
                            const UA_NodeId& nodeId, 
                            std::function<void(const T&)> callback) 
{
    // 1. Allocate the context on the heap. 
    // This MUST be on the heap so it survives after this function returns.
    auto* ctx = new MonitoredItemContext<T>{ std::move(callback) };

    // 2. Setup the request
    UA_MonitoredItemCreateRequest monRequest = UA_MonitoredItemCreateRequest_default(nodeId);
    
    // Optional: tweak sampling interval (e.g., 500ms)
    monRequest.requestedParameters.samplingInterval = 500.0; 

    // 3. Register with open62541
    UA_MonitoredItemCreateResult monResponse = UA_Client_MonitoredItems_createDataChange(
        client, 
        subscriptionId, 
        UA_TIMESTAMPSTORETURN_BOTH, 
        monRequest, 
        ctx,                            // Pass our heap pointer as the void* context
        data_change_callback<T>,        // Function pointer to process data
        delete_monitored_item_callback<T> // Function pointer to clean up memory
    );

    // 4. Handle failure
    if (monResponse.statusCode != UA_STATUSCODE_GOOD) {
        delete ctx; // Clean up manually if registration failed!
        return 0;
    }

    return monResponse.monitoredItemId;
}

void setup_subscriptions(UA_Client* client, UA_UInt32 masterSubId) {
    UA_NodeId pumpSpeedId = UA_NODEID_NUMERIC(1, 1002);
    UA_NodeId pumpNameId = UA_NODEID_STRING(1, "PumpName");

    // Subscribe to an integer
    subscribe_to_node<int32_t>(client, masterSubId, pumpSpeedId, [](const int32_t& newSpeed) {
        std::cout << "Pump speed changed to: " << newSpeed << " RPM\n";
    });

    // Subscribe to a string and capture local variables!
    int update_count = 0;
    subscribe_to_node<std::string>(client, masterSubId, pumpNameId,(const std::string& newName) {
        update_count++;
        std::cout << "Name changed to " << newName << " (Total updates: " << update_count << ")\n";
    });
}


#include <open62541/client_subscriptions.h>
#include <iostream>
#include <optional>

// Returns the Subscription ID if successful, or std::nullopt if it fails
std::optional<UA_UInt32> create_master_subscription(UA_Client* client) {
    
    // 1. Setup the standard request
    UA_CreateSubscriptionRequest request = UA_CreateSubscriptionRequest_default();

    // 2. Configure the "Heartbeat" (Crucial for performance!)
    // This tells the server: "Check my monitored items and send me an update every 500ms"
    request.requestedPublishingInterval = 500.0; 
    
    // How many times the server can skip sending a message if data hasn't changed
    request.requestedMaxKeepAliveCount = 10; 
    
    // How many intervals the server waits before considering your client disconnected
    request.requestedLifetimeCount = 30; 

    // 3. Execute the request
    UA_CreateSubscriptionResponse response = UA_Client_Subscriptions_create(
        client, 
        request, 
        nullptr, // We don't need a global context for the subscription itself
        nullptr, // No global status change callback needed for this basic setup
        nullptr  // No global delete callback needed
    );

    // 4. Check for success
    if (response.responseHeader.serviceResult != UA_STATUSCODE_GOOD) {
        std::cerr << "Failed to create master subscription!\n";
        return std::nullopt;
    }

    std::cout << "Master subscription created with ID: " << response.subscriptionId << "\n";
    return response.subscriptionId;
}

void opc_thread_entry(UA_Client* client) {
    // 1. First, connect the client to the server
    UA_StatusCode connectStatus = UA_Client_connect(client, "opc.tcp://192.168.1.100:4840");
    if (connectStatus != UA_STATUSCODE_GOOD) {
        return; // Handle connection failure
    }

    // 2. Create the master subscription truck
    auto maybeSubId = create_master_subscription(client);
    if (!maybeSubId.has_value()) {
        return; // Handle subscription failure
    }
    UA_UInt32 masterSubId = maybeSubId.value();

    // 3. Load your packages (Monitored Items) onto the truck!
    // (Using the subscribe_to_node function we wrote earlier)
    UA_NodeId pumpSpeedId = UA_NODEID_NUMERIC(1, 1002);
    
    subscribe_to_node<int32_t>(client, masterSubId, pumpSpeedId, [](const int32_t& speed) {
        std::cout << "Live Speed: " << speed << "\n";
    });

    // 4. Enter the infinite RTOS loop to process incoming network traffic
    while (true) {
        // This function blocks briefly, receives the network packets, 
        // and synchronously fires your lambdas if data changed!
        UA_Client_run_iterate(client, 100); 
        
        // ... (yield thread, sleep, etc.) ...
    }
}


template <typename T, typename Variant>
consteval std::size_t get_variant_index() {
    // 1. Pretend to pass a Variant pointer to an explicit template lambda
    return []<typename... Ts>(const std::variant<Ts...>*) {
        
        // 2. Build a compile-time array of booleans checking if each type matches T
        constexpr std::array<bool, sizeof...(Ts)> matches = { std::is_same_v<T, Ts>... };
        
        std::size_t match_count = 0;
        std::size_t found_index = 0;
        
        // 3. Loop through the array to find our match
        for (std::size_t i = 0; i < matches.size(); ++i) {
            if (matches[i]) {
                found_index = i;
                match_count++;
            }
        }
        
        // 4. Compile-time assertions
        // consteval functions are not allowed to throw exceptions. 
        // If these throw statements are hit, compilation fails immediately 
        // and prints your custom error message in the compiler output!
        if (match_count == 0) throw "Error: Type not found in variant!";
        if (match_count > 1) throw "Error: Type is not unique in variant!";
        
        return found_index;
        
    }(static_cast<Variant*>(nullptr));
}

@startuml class_diagram
skinparam classAttributeIconSize 0

hide <<utility>> circles

namespace OPC_UA {
    class Client {
        + <<alias>> BrowseResult

        + connect() : void
        + disconnect() : void
    }

    class Server {
        + start() : void
        + stop() : void
    }

    class Read <<utility>> {
        + {static} readNode() : void
    }

    class Write <<utility>> {
        + {static} writeNode() : void
    }

    class Subscription <<utility>> {
        + {static} createSubscription() : void
        + {static} subscribeNode() : void
    }
}

interface IExecutor {
    + {abstract} initialize() : void
    + {abstract} execute() : void
}

struct StandbyOperatingScheme {}

namespace Server {
    namespace Bioreactor {
    }
    namespace ProcessingStation {
    }
}

namespace EquipmentPhases {
    abstract class "BaseEquipmentPhase<Derived, EM, OutputData, OperatingScheme...>" as BaseEquipmentPhase implements .IExecutor {
        - m_topic : string_view
        + {abstract} foo() : void
    }

    namespace Bioreactor {
    class DummyPhase extends EquipmentPhases.BaseEquipmentPhase {
            + initialize() : void
            + execute() : void
        } 
    }
}

namespace EquipmentModules {

    abstract class "BaseEquipmentModule<Derived = ProcessingStation::DummyModule\nEM = ProcessingStation::DummyParameters\nOutputData = ProcessingStation::DummyOutputData\nOperatingScheme... = {ProcessingStation::DummyOperatingScheme}>" as BaseEquipmentModule implements .IExecutor {
        - m_topic : string_view
        + {abstract} foo() : void
    }

    namespace Bioreactor {
        class "RemoteModule<EM = ProcessingStation::DummyModule>" as RemoteModule implements .IExecutor {
            + <<alias>> EMParams : EM::BaseEquipmentModule::EM
            + <<alias>> EMOutputData : EM::BaseEquipmentModule::OutputData
            + <<alias>> EMOperatingScheme : EM::BaseEquipmentModule::OperatingScheme
            + <<alias>> OperatingSchemes : {StandbyOperatingScheme, EMOperatingScheme}

            + initialize() : void
            + execute() : void
            - waitForClient(): void
            - broseRemoteEM(): void
            - subscribeRemoteOutputs() : void
            - subscribeLocalOperatingSchemes() : void
        }
    }

    namespace ProcessingStation {
        struct DummyOperatingScheme {
            + param1 : int
            + param2 : string
        }

        struct DummyParameters {
            + param1 : int
            + param2 : string
        }

        struct DummyOutputData {
            + param1 : int
            + param2 : string
        }

        class DummyModule extends EquipmentModules.BaseEquipmentModule {
            + initialize() : void
            + execute() : void
        } 
    }

    BaseEquipmentModule ..> ProcessingStation.DummyParameters : <<use>>
    BaseEquipmentModule ..> ProcessingStation.DummyOutputData : <<use>>
    BaseEquipmentModule ..> ProcessingStation.DummyOperatingScheme : <<use>>
    BaseEquipmentModule ..> ProcessingStation.DummyModule : <<use>>

    Bioreactor.RemoteModule ...> ProcessingStation.DummyModule : <<use>>
    Bioreactor.RemoteModule ..> .StandbyOperatingScheme : <<use>>
}

namespace ControlModules {

}

EquipmentPhases.Bioreactor.DummyPhase <.[#DarkBlue,thickness=2].> EquipmentModules.Bioreactor.RemoteModule : <color:DarkBlue><<msg_queue>></color>
EquipmentModules.Bioreactor.RemoteModule <.[#DarkBlue,thickness=2].> EquipmentModules.ProcessingStation.DummyModule : <color:DarkBlue><<opc_ua>></color>

@enduml

