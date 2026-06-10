template<auto MemberPtr>
    requires std::is_member_object_pointer_v<decltype(MemberPtr)>
constexpr size_t member_index()
{
    using Object = get_class_type_t<decltype(MemberPtr)>;
    Object dummy{};

    auto offset{ std::numeric_limits<size_t>::max() };
    reflect::for_each([&](const auto I) {
        if (static_cast<void*>(&reflect::get<I>(dummy)) == static_cast<void*>(&(dummy.*MemberPtr))) {
            offset = I;
        }
    }, dummy);

    assert(offset != std::numeric_limits<size_t>::max());
    return offset;
}

template<auto Register>
    requires requires {
        { get_class_type_t<decltype(Register)>::BASE_ADDRESS } -> std::convertible_to<uint16_t>;
    }
constexpr uint16_t calculateRegisterAddress()
{
    using Registers = get_class_type_t<decltype(Register)>;
    constexpr auto index{ member_index<Register>() };
    constexpr auto byteOffset{ reflect::offset_of<index, Registers>() };
    constexpr auto registerOffset{ byteOffset / sizeof(uint16_t) };
    return static_cast<uint16_t>(Registers::BASE_ADDRESS + registerOffset);
}



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

#include <open62541/client_config_default.h>
#include <open62541/client_highlevel_async.h>

#include <chrono>
#include <iostream>
#include <memory>
#include <string>

class OpcUaClient {
public:
    // Delete default constructor, copy, and move semantics to prevent dangling pointers
    OpcUaClient() = delete;
    OpcUaClient(const OpcUaClient&) = delete;
    OpcUaClient& operator=(const OpcUaClient&) = delete;

    /**
     * @brief Constructs the OPC UA Client.
     * @param endpoint The OPC UA server URL (e.g., "opc.tcp://192.168.1.100:4840")
     */
    explicit OpcUaClient(std::string endpoint) 
        : endpoint_(std::move(endpoint)) 
    {
        // 1. Initialize the raw C pointer inside our smart pointer
        client_.reset(UA_Client_new());
        
        // 2. Set default config and customize the timeout
        UA_ClientConfig* config = UA_Client_getConfig(client_.get());
        UA_ClientConfig_setDefault(config);
        config->timeout = 3000; // 3 seconds is a safe sweet spot for embedded servers
    }

    /**
     * @brief The single update function to be called in your main thread loop.
     * It handles async reconnections, backoff timers, and network traffic polling.
     * This function will never block the thread.
     */
    void execute() {
        UA_ClientState state = UA_Client_getState(client_.get());

        // 1. Connection State Machine
        if (state == UA_CLIENTSTATE_DISCONNECTED) {
            auto now = std::chrono::steady_clock::now();
            
            // Initiate a connection ONLY if we aren't currently trying, 
            // and our backoff timer has expired.
            if (!is_connecting_ && now >= next_retry_time_) {
                std::cout << "[Client] Initiating connection to " << endpoint_ << "...\n";
                is_connecting_ = true;
                
                // Pass 'this' as the userdata so the C-callback can update this specific object
                UA_Client_connectAsync(client_.get(), endpoint_.c_str(), &OpcUaClient::onConnectCallback, this);
            }
        } 
        else if (state == UA_CLIENTSTATE_SESSION) {
            // The client is connected and healthy.
            // If you have async Read/Write/Call requests, you can enqueue them here.
        }

        // 2. Process all pending background network operations (non-blocking)
        UA_Client_run_iterate(client_.get(), 0);
    }

private:
    // Custom deleter for std::unique_ptr to safely clean up the open62541 client
    struct UA_ClientDeleter {
        void operator()(UA_Client* c) const {
            if (c) {
                // Disconnect cleanly if a session is active, then delete
                UA_Client_disconnect(c); 
                UA_Client_delete(c);
            }
        }
    };

    std::unique_ptr<UA_Client, UA_ClientDeleter> client_{nullptr};
    std::string endpoint_;
    
    // State machine tracking
    bool is_connecting_{false};
    std::chrono::steady_clock::time_point next_retry_time_{};
    std::chrono::milliseconds retry_backoff_{5000}; // 5-second delay on failure

    /**
     * @brief The static C-style callback triggered by open62541 when connectAsync finishes.
     */
    static void onConnectCallback(UA_Client* /*client*/, void* userdata, UA_UInt32 /*requestId*/, UA_StatusCode status) {
        // Cast the userdata back to our C++ class instance
        auto* self = static_cast<OpcUaClient*>(userdata);
        
        // Unlock the connection state
        self->is_connecting_ = false;

        if (status == UA_STATUSCODE_GOOD) {
            std::cout << "[Client] Connected successfully to " << self->endpoint_ << "!\n";
        } else {
            std::cout << "[Client] Connection failed: " << UA_StatusCode_name(status) 
                      << ". Retrying in " << self->retry_backoff_.count() << "ms.\n";
            
            // Set the backoff timer for the next attempt
            self->next_retry_time_ = std::chrono::steady_clock::now() + self->retry_backoff_;
        }
    }
};











#include <open62541/client_config_default.h>
#include <open62541/client_highlevel_async.h>
#include <open62541/client.h>

#include <chrono>
#include <iostream>
#include <memory>
#include <string>

class OpcUaClient {
public:
    OpcUaClient() = delete;
    OpcUaClient(const OpcUaClient&) = delete;
    OpcUaClient& operator=(const OpcUaClient&) = delete;

    explicit OpcUaClient(std::string endpoint) 
        : endpoint_(std::move(endpoint)) 
    {
        client_.reset(UA_Client_new());
        UA_ClientConfig* config = UA_Client_getConfig(client_.get());
        UA_ClientConfig_setDefault(config);
        
        config->timeout = 3000; 
        
        // 1. Pass 'this' into the context so the C-callback can interact with our C++ class
        config->clientContext = this; 
        
        // 2. Register the modern open62541 state callback
        config->stateCallback = &OpcUaClient::onStateChange;
    }

    void execute() {
        UA_SecureChannelState channelState;
        UA_SessionState sessionState;
        UA_StatusCode connectStatus;

        // 3. The modern 4-parameter getState function
        UA_Client_getState(client_.get(), &channelState, &sessionState, &connectStatus);

        // 4. Connection State Machine logic
        if (channelState == UA_SECURECHANNELSTATE_CLOSED && !is_connecting_) {
            auto now = std::chrono::steady_clock::now();
            
            if (now >= next_retry_time_) {
                std::cout << "[Client] Initiating async connection to " << endpoint_ << "...\n";
                is_connecting_ = true;
                
                // 5. The modern connectAsync (no callback parameters required)
                UA_StatusCode retval = UA_Client_connectAsync(client_.get(), endpoint_.c_str());
                
                if (retval != UA_STATUSCODE_GOOD) {
                    // Rejected immediately (e.g., DNS resolution failed)
                    is_connecting_ = false;
                    next_retry_time_ = now + retry_backoff_;
                    std::cout << "[Client] connectAsync rejected: " << UA_StatusCode_name(retval) << "\n";
                }
            }
        } 
        else if (sessionState == UA_SESSIONSTATE_ACTIVATED) {
            // The client is fully connected and active!
            // Enqueue async Read/Write/Call requests here.
        }

        // 6. Keep the background thread moving (Non-blocking)
        UA_Client_run_iterate(client_.get(), 0);
    }

private:
    // Custom deleter for safe cleanup
    struct UA_ClientDeleter {
        void operator()(UA_Client* c) const {
            if (c) {
                // Clear the context so callbacks during shutdown are safely ignored
                UA_ClientConfig* config = UA_Client_getConfig(c);
                if (config) config->clientContext = nullptr;
                
                UA_Client_disconnect(c);
                UA_Client_delete(c);
            }
        }
    };

    std::unique_ptr<UA_Client, UA_ClientDeleter> client_{nullptr};
    std::string endpoint_;
    
    bool is_connecting_{false};
    std::chrono::steady_clock::time_point next_retry_time_{};
    std::chrono::milliseconds retry_backoff_{5000}; 

    /**
     * @brief The modern C-style callback triggered by open62541 state changes.
     */
    static void onStateChange(UA_Client *client, UA_SecureChannelState channelState, 
                              UA_SessionState sessionState, UA_StatusCode connectStatus) {
        
        // Retrieve our C++ object back from the client configuration context
        auto* self = static_cast<OpcUaClient*>(UA_Client_getContext(client));
        if (!self) return; // Safely ignore if tearing down

        if (sessionState == UA_SESSIONSTATE_ACTIVATED) {
            self->is_connecting_ = false;
            std::cout << "[Client] Connection ESTABLISHED to " << self->endpoint_ << "!\n";
        } 
        else if (channelState == UA_SECURECHANNELSTATE_CLOSED) {
            // Whether the async connect failed, or an active connection just dropped,
            // we unlock the state and enforce a backoff timer before retrying.
            self->is_connecting_ = false;
            std::cout << "[Client] Connection closed or failed. Status: " 
                      << UA_StatusCode_name(connectStatus) << "\n";
            self->next_retry_time_ = std::chrono::steady_clock::now() + self->retry_backoff_;
        }
    }
};























#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import os
import select
import shlex
import shutil
import signal
import subprocess
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
RUNTIME_DIR = Path(os.environ.get("COMMDEV_SERIAL_RUNTIME", "/tmp/commdev-serial"))
STATE_PATH = RUNTIME_DIR / "state.json"
SOCAT_LOG = RUNTIME_DIR / "socat.log"
DEFAULT_LINUX_LINK = RUNTIME_DIR / "linux-port"
DEFAULT_WINE_LINK = RUNTIME_DIR / "wine-port"
DEFAULT_WINE_PAYLOAD_FILE = RUNTIME_DIR / "wine-smoke.txt"
DEFAULT_COM_PORT = os.environ.get("COMMDEV_WINE_COM_PORT", "COM5")
DEFAULT_TIMEOUT_SECONDS = float(os.environ.get("COMMDEV_SERIAL_SMOKE_TIMEOUT", "8"))
DEFAULT_WINEPREFIX = Path(os.environ.get("WINEPREFIX", str(Path.home() / ".commdev-wine")))


def run(
    command: list[str],
    *,
    check: bool = True,
    capture: bool = False,
    quiet: bool = False,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    kwargs: dict[str, object] = {"cwd": ROOT, "text": True, "check": check, "env": env}

    if capture:
        kwargs["capture_output"] = True
    elif quiet:
        kwargs["stdout"] = subprocess.DEVNULL
        kwargs["stderr"] = subprocess.DEVNULL

    return subprocess.run(command, **kwargs)


def ensure_command(command_name: str) -> str:
    resolved = shutil.which(command_name)
    if resolved:
        return resolved

    raise SystemExit(f"Required command is not available: {command_name}")


def ensure_runtime_dir() -> None:
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)


def load_state() -> dict[str, object] | None:
    if not STATE_PATH.exists():
        return None

    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Failed to parse {STATE_PATH}: {exc}") from exc


def save_state(state: dict[str, object]) -> None:
    ensure_runtime_dir()
    STATE_PATH.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def process_running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except OSError:
        return False

    return True


def remove_path(path: Path) -> None:
    if path.is_symlink() or path.exists():
        path.unlink()


def wine_env(prefix: Path) -> dict[str, str]:
    env = os.environ.copy()
    env["WINEPREFIX"] = str(prefix)
    return env


def ensure_wine_ready(prefix: Path) -> None:
    ensure_command("wine")
    ensure_command("wineboot")

    prefix.parent.mkdir(parents=True, exist_ok=True)

    if (prefix / "dosdevices").exists():
        return

    print(f"Initializing Wine prefix at {prefix}...", flush=True)
    run(["wineboot", "-u"], env=wine_env(prefix))

    if not (prefix / "dosdevices").exists():
        raise SystemExit(f"Wine prefix initialization did not create {prefix / 'dosdevices'}")


def com_port_name(raw_name: str) -> tuple[str, str]:
    normalized = raw_name.strip().upper()
    if not normalized.startswith("COM") or not normalized[3:].isdigit():
        raise SystemExit(f"Invalid COM port name: {raw_name}")

    return normalized, normalized.lower()


def mapping_path(prefix: Path, com_port: str) -> Path:
    _, device_name = com_port_name(com_port)
    return prefix / "dosdevices" / device_name


def wine_drive_path(path: Path) -> str:
    return "Z:" + path.as_posix().replace("/", "\\")


def wait_for_links(paths: list[Path], pid: int, timeout_seconds: float = 8.0) -> None:
    deadline = time.monotonic() + timeout_seconds

    while time.monotonic() < deadline:
        if all(path.exists() for path in paths):
            return

        if not process_running(pid):
            raise SystemExit(f"socat exited before creating PTY links. Check {SOCAT_LOG} for details.")

        time.sleep(0.1)

    missing = ", ".join(str(path) for path in paths if not path.exists())
    raise SystemExit(f"Timed out waiting for PTY links: {missing}")


def start_socat(linux_link: Path, wine_link: Path) -> int:
    ensure_command("socat")
    ensure_runtime_dir()

    remove_path(linux_link)
    remove_path(wine_link)

    with SOCAT_LOG.open("w", encoding="utf-8") as log_file:
        process = subprocess.Popen(
            [
                "socat",
                "-d",
                "-d",
                f"pty,raw,echo=0,link={linux_link}",
                f"pty,raw,echo=0,link={wine_link}",
            ],
            cwd=ROOT,
            stdout=subprocess.DEVNULL,
            stderr=log_file,
            text=True,
        )

    wait_for_links([linux_link, wine_link], process.pid)
    return process.pid


def create_com_mapping(prefix: Path, com_port: str, target: Path) -> Path:
    mapping = mapping_path(prefix, com_port)

    if mapping.is_symlink():
        if Path(os.path.realpath(mapping)) == target:
            return mapping

        raise SystemExit(
            f"Wine mapping {mapping} already exists and points to {os.path.realpath(mapping)}. "
            f"Choose a different COM port or remove the existing mapping first."
        )

    if mapping.exists():
        raise SystemExit(f"Wine mapping {mapping} already exists and is not a symlink.")

    mapping.symlink_to(target)
    return mapping


def read_status(state: dict[str, object]) -> dict[str, object]:
    socat_pid = int(state["socat_pid"])
    wine_prefix = Path(str(state["wine_prefix"]))
    com_port = str(state["com_port"])
    mapping = mapping_path(wine_prefix, com_port)

    return {
        **state,
        "running": process_running(socat_pid),
        "mapping_path": str(mapping),
        "mapping_target": os.path.realpath(mapping) if mapping.is_symlink() else "",
        "linux_link_exists": Path(str(state["linux_link"])).exists(),
        "wine_link_exists": Path(str(state["wine_link"])).exists(),
    }


def print_status(state: dict[str, object]) -> None:
    status = read_status(state)
    windows_payload_file = wine_drive_path(DEFAULT_WINE_PAYLOAD_FILE)
    print(f"socat pid: {status['socat_pid']}")
    print(f"running: {status['running']}")
    print(f"linux port: {status['linux_link']}")
    print(f"wine port link: {status['wine_link']}")
    print(f"wine port realpath: {status['wine_realpath']}")
    print(f"Wine prefix: {status['wine_prefix']}")
    print(f"COM mapping: {status['com_port']} -> {status['mapping_target'] or '<missing>'}")
    print(f"socat log: {SOCAT_LOG}")
    print()
    print("Manual smoke test:")
    print(f"  cat {shlex.quote(str(Path(str(status['linux_link']))))}")
    print(
        "  "
        + shlex.join(
            [
                "env",
                f"WINEPREFIX={status['wine_prefix']}",
                "wine",
                "cmd",
                "/c",
                f"echo hello-from-wine>{windows_payload_file} && copy /b {windows_payload_file} {status['com_port']} >NUL",
            ]
        )
    )


def stop_process(pid: int) -> None:
    if not process_running(pid):
        return

    os.kill(pid, signal.SIGTERM)
    deadline = time.monotonic() + 5.0

    while time.monotonic() < deadline:
        if not process_running(pid):
            return

        time.sleep(0.1)

    os.kill(pid, signal.SIGKILL)


def cleanup_state(state: dict[str, object] | None) -> None:
    if state is None:
        for path in (DEFAULT_LINUX_LINK, DEFAULT_WINE_LINK, DEFAULT_WINE_PAYLOAD_FILE, STATE_PATH):
            if path == STATE_PATH:
                if path.exists():
                    path.unlink()
            else:
                remove_path(path)
        return

    if "socat_pid" in state:
        stop_process(int(state["socat_pid"]))

    wine_prefix = Path(str(state["wine_prefix"]))
    com_port = str(state["com_port"])
    mapping = mapping_path(wine_prefix, com_port)
    expected_target = str(state.get("wine_realpath", ""))

    if mapping.is_symlink() and os.path.realpath(mapping) == expected_target:
        mapping.unlink()

    for key in ("linux_link", "wine_link"):
        remove_path(Path(str(state[key])))

    remove_path(DEFAULT_WINE_PAYLOAD_FILE)

    if STATE_PATH.exists():
        STATE_PATH.unlink()


def stale_state_cleanup() -> None:
    state = load_state()
    if state is None:
        return

    if process_running(int(state["socat_pid"])):
        return

    cleanup_state(state)


def ensure_started(com_port: str, prefix: Path) -> dict[str, object]:
    stale_state_cleanup()
    state = load_state()
    normalized_com_port, _ = com_port_name(com_port)

    if state is not None and process_running(int(state["socat_pid"])):
        existing_com_port = str(state["com_port"])
        existing_prefix = Path(str(state["wine_prefix"]))
        if existing_com_port != normalized_com_port or existing_prefix != prefix:
            raise SystemExit(
                f"Serial lab is already running with {existing_com_port} and {existing_prefix}. Run down first."
            )

        return state

    ensure_wine_ready(prefix)

    socat_pid = start_socat(DEFAULT_LINUX_LINK, DEFAULT_WINE_LINK)
    wine_realpath = Path(os.path.realpath(DEFAULT_WINE_LINK))
    create_com_mapping(prefix, normalized_com_port, wine_realpath)

    state = {
        "com_port": normalized_com_port,
        "linux_link": str(DEFAULT_LINUX_LINK),
        "linux_realpath": os.path.realpath(DEFAULT_LINUX_LINK),
        "socat_pid": socat_pid,
        "wine_link": str(DEFAULT_WINE_LINK),
        "wine_prefix": str(prefix),
        "wine_realpath": str(wine_realpath),
    }
    save_state(state)
    return state


def status_command(com_port: str, prefix: Path) -> int:
    stale_state_cleanup()
    state = load_state()
    if state is None:
        print("Serial lab is not running.")
        return 1

    expected_com_port, _ = com_port_name(com_port)
    if str(state["com_port"]) != expected_com_port or Path(str(state["wine_prefix"])) != prefix:
        raise SystemExit(
            f"Serial lab is running with {state['com_port']} and {state['wine_prefix']}. "
            f"Requested {expected_com_port} and {prefix}."
        )

    print_status(state)
    return 0


def escape_cmd_echo_payload(payload: str) -> str:
    unsupported = set("&|<>^")
    bad = sorted(character for character in payload if character in unsupported)
    if bad:
        joined = " ".join(sorted(set(bad)))
        raise SystemExit(f"Payload contains unsupported cmd.exe metacharacters: {joined}")

    return payload


def read_cat_line(cat_process: subprocess.Popen[str], timeout_seconds: float) -> str:
    if cat_process.stdout is None:
        raise SystemExit("cat stdout was not captured")

    ready, _, _ = select.select([cat_process.stdout], [], [], timeout_seconds)
    if not ready:
        raise SystemExit("Timed out waiting for data on the Linux PTY")

    line = cat_process.stdout.readline()
    if line == "":
        stderr_output = ""
        if cat_process.stderr is not None:
            stderr_output = cat_process.stderr.read().strip()
        raise SystemExit(f"cat exited before any PTY data was received. {stderr_output}".strip())

    return line


def run_wine_echo(prefix: Path, com_port: str, payload: str) -> None:
    safe_payload = escape_cmd_echo_payload(payload)
    payload_file = DEFAULT_WINE_PAYLOAD_FILE
    payload_file.parent.mkdir(parents=True, exist_ok=True)
    command = [
        "wine",
        "cmd",
        "/c",
        f"echo {safe_payload}>{wine_drive_path(payload_file)} && copy /b {wine_drive_path(payload_file)} {com_port} >NUL",
    ]
    run(command, env=wine_env(prefix))


def cat_listener_command(device_path: Path) -> list[str]:
    if shutil.which("stdbuf"):
        return ["stdbuf", "-o0", "cat", str(device_path)]

    return ["cat", str(device_path)]


def smoke_command(com_port: str, prefix: Path, payload: str, timeout_seconds: float) -> int:
    state = ensure_started(com_port, prefix)
    linux_link = Path(str(state["linux_link"]))
    cat_process = subprocess.Popen(
        cat_listener_command(linux_link),
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    try:
        time.sleep(0.2)
        run_wine_echo(prefix, str(state["com_port"]), payload)
        received = read_cat_line(cat_process, timeout_seconds)
        normalized = received.rstrip("\r\n")
        if payload == payload.rstrip() and normalized.rstrip() == payload:
            normalized = normalized.rstrip()
        if normalized != payload:
            raise SystemExit(f"Smoke test failed: expected {payload!r}, received {normalized!r}")
    finally:
        cat_process.terminate()
        try:
            cat_process.wait(timeout=2.0)
        except subprocess.TimeoutExpired:
            cat_process.kill()
            cat_process.wait(timeout=2.0)

    print(f"Smoke test passed: received {normalized!r} on {linux_link}")
    return 0


def up_command(com_port: str, prefix: Path) -> int:
    state = ensure_started(com_port, prefix)
    print_status(state)
    return 0


def down_command() -> int:
    state = load_state()
    cleanup_state(state)
    print("Serial lab stopped.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Create and verify a Wine-to-Linux PTY bridge.")
    parser.add_argument("command", choices=["up", "status", "smoke", "down"], nargs="?", default="status")
    parser.add_argument("--com-port", default=DEFAULT_COM_PORT)
    parser.add_argument("--wine-prefix", default=str(DEFAULT_WINEPREFIX))
    parser.add_argument("--payload", default="hello-from-wine")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT_SECONDS)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    prefix = Path(args.wine_prefix).expanduser().resolve()

    if args.command == "up":
        return up_command(args.com_port, prefix)

    if args.command == "status":
        return status_command(args.com_port, prefix)

    if args.command == "smoke":
        return smoke_command(args.com_port, prefix, args.payload, args.timeout)

    if args.command == "down":
        return down_command()

    raise SystemExit(f"Unsupported command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())


dpkg --add-architecture i386 \
wine \
wine32 \
wine64 \
winbind \



#!/usr/bin/env bash
set -euo pipefail

DIR=/tmp/commdev-serial
PIDFILE=$DIR/socat.pid
LOG=$DIR/socat.log
LINUX_PORT=$DIR/linux-port
WINE_PORT=$DIR/wine-port
PAYLOAD=$DIR/wine-smoke.txt
OUTPUT=$DIR/linux-read.txt
WINEPREFIX=/home/vscode/.wine-commdev
COM=COM5
COM_LINK=$WINEPREFIX/dosdevices/com5
WIN_PAYLOAD='Z:\tmp\commdev-serial\wine-smoke.txt'
CMD=${1:-up}

smoke_once() {
    rm -f "$PAYLOAD" "$OUTPUT"
    WINEPREFIX="$WINEPREFIX" wineserver -p >/dev/null 2>&1 || true
    WINEPREFIX="$WINEPREFIX" wine cmd /c exit >/dev/null 2>&1 || true
    rm -f "$COM_LINK"
    ln -s "$(readlink -f "$WINE_PORT")" "$COM_LINK"
    stdbuf -o0 cat "$LINUX_PORT" > "$OUTPUT" &
    CATPID=$!
    sleep 1
    WINEPREFIX="$WINEPREFIX" wine cmd /c "echo hello-from-wine>$WIN_PAYLOAD && copy /b $WIN_PAYLOAD $COM >NUL" >/dev/null 2>&1 || true
    sleep 1
    kill "$CATPID" 2>/dev/null || true
    wait "$CATPID" 2>/dev/null || true
    LINE=$(tr -d '\r' < "$OUTPUT" | head -n 1 | sed 's/[[:space:]]*$//')
    [[ "$LINE" == "hello-from-wine" ]]
}

if [[ "$CMD" == down ]]; then
    [[ -f "$PIDFILE" ]] && kill "$(cat "$PIDFILE")" 2>/dev/null || true
    WINEPREFIX="$WINEPREFIX" wineserver -k >/dev/null 2>&1 || true
    rm -f "$PIDFILE" "$LINUX_PORT" "$WINE_PORT" "$PAYLOAD" "$OUTPUT" "$COM_LINK"
    echo "stopped"
    exit 0
fi

command -v socat >/dev/null
command -v wine >/dev/null
command -v wineserver >/dev/null
mkdir -p "$DIR" "$WINEPREFIX"

if [[ ! -d "$WINEPREFIX/dosdevices" ]]; then
    WINEPREFIX="$WINEPREFIX" wineboot -u >/dev/null 2>&1 || true
fi

if [[ "$CMD" == up ]]; then
    [[ -f "$PIDFILE" ]] && kill "$(cat "$PIDFILE")" 2>/dev/null || true
    rm -f "$PIDFILE" "$LINUX_PORT" "$WINE_PORT" "$PAYLOAD" "$OUTPUT" "$COM_LINK"
    socat -d -d "pty,raw,echo=0,link=$LINUX_PORT" "pty,raw,echo=0,link=$WINE_PORT" >/dev/null 2>"$LOG" &
    echo $! > "$PIDFILE"
    for _ in {1..80}; do
        [[ -e "$LINUX_PORT" && -e "$WINE_PORT" ]] && break
        sleep 0.1
    done
    WINEPREFIX="$WINEPREFIX" wineserver -p >/dev/null 2>&1 || true
    WINEPREFIX="$WINEPREFIX" wine cmd /c exit >/dev/null 2>&1 || true
    ln -s "$(readlink -f "$WINE_PORT")" "$COM_LINK"
    echo "linux: $LINUX_PORT"
    echo "wine:  $WINE_PORT"
    echo "com:   $COM -> $(readlink -f "$COM_LINK")"
    exit 0
fi

if [[ "$CMD" == smoke ]]; then
    "$0" up >/dev/null
    if ! smoke_once; then
        "$0" up >/dev/null
        smoke_once || {
            echo "${LINE:-not ready}"
            exit 1
        }
    fi
    echo "$LINE"
    exit 0
fi

echo "usage: $0 [up|smoke|down]" >&2
exit 1












#include <gmock/gmock.h>
#include <gtest/gtest.h>

#include "HAL/Implementation/HLDriver/WVS.hpp"
#include "HAL/Interfaces/HLDriver/IModbusASCII.hpp"

using namespace testing;
using namespace HAL::Implementation::HLDriver;

namespace {

class MockModbusASCII final : public HAL::Interfaces::HLDriver::IModbusASCII {
public:
    MOCK_METHOD(std::vector<uint16_t>,
                readHoldingRegister,
                (uint16_t address, uint16_t quantity),
                (override));

    MOCK_METHOD(bool,
                writeRegister,
                (uint16_t address, const std::vector<uint16_t>& values),
                (override));
};

class WVSTest : public Test {
protected:
    MockModbusASCII* mock{};
    std::unique_ptr<WVS> sut;

    void SetUp() override {
        auto driver = std::make_unique<StrictMock<MockModbusASCII>>();
        mock = driver.get();
        sut = std::make_unique<WVS>(std::move(driver));
    }
};

TEST_F(WVSTest, getCurrentStateReadsCurrentStateRegister) {
    EXPECT_CALL(*mock, readHoldingRegister(0x0064, 1))
        .WillOnce(Return(std::vector<uint16_t>{2}));

    auto result = sut->getCurrentState();

    ASSERT_TRUE(result.has_value());
    EXPECT_EQ(*result, static_cast<WVS::State>(2));
}

TEST_F(WVSTest, isTHDisplacementDemandedReadsTHDisplacementRegister) {
    EXPECT_CALL(*mock, readHoldingRegister(0x0066, 1))
        .WillOnce(Return(std::vector<uint16_t>{1}));

    auto result = sut->isTHDisplacementDemanded();

    ASSERT_TRUE(result.has_value());
    EXPECT_TRUE(*result);
}

TEST_F(WVSTest, resetTHDisplacementDemandWritesFalseToTHDisplacementRegister) {
    EXPECT_CALL(*mock, writeRegister(0x0066, ElementsAre(0)))
        .WillOnce(Return(true));

    EXPECT_TRUE(sut->resetTHDisplacementDemand());
}

TEST_F(WVSTest, sendCommandWritesCommandToActionDemandRegister) {
    auto cmd = static_cast<WVS::Command>(3);

    EXPECT_CALL(*mock, writeRegister(0x00C8, ElementsAre(3)))
        .WillOnce(Return(true));

    EXPECT_TRUE(sut->sendCommand(cmd));
}

TEST_F(WVSTest, disableReopeningWritesFalseToReopeningDemandRegister) {
    EXPECT_CALL(*mock, writeRegister(0x00C9, ElementsAre(0)))
        .WillOnce(Return(true));

    EXPECT_TRUE(sut->disableReopening());
}

TEST_F(WVSTest, enableReopeningWritesTrueToReopeningDemandRegister) {
    EXPECT_CALL(*mock, writeRegister(0x00C9, ElementsAre(1)))
        .WillOnce(Return(true));

    EXPECT_TRUE(sut->enableReopening());
}

TEST_F(WVSTest, getStatusReadsStatusRegisterBlock) {
    EXPECT_CALL(*mock, readHoldingRegister(0x0064, 6))
        .WillOnce(Return(std::vector<uint16_t>{
            2,      // currentState
            1,      // previousState
            1,      // thDisplacement
            7,      // resetCause
            0x0001, // uptime_msb
            0x0002  // uptime_lsb
        }));

    auto result = sut->getStatus();

    ASSERT_TRUE(result.has_value());
    EXPECT_EQ(result->currentState, static_cast<WVS::State>(2));
    EXPECT_EQ(result->previousState, static_cast<WVS::State>(1));
    EXPECT_TRUE(result->thDisplacement);
    EXPECT_EQ(result->resetCause, 7);
}

TEST_F(WVSTest, getStatusReturnsNulloptIfRegisterReadNeverReturnsExpectedSize) {
    EXPECT_CALL(*mock, readHoldingRegister(0x0064, 6))
        .Times(4) // MAX_RETRIES is 3, loop uses <=, so 4 attempts
        .WillRepeatedly(Return(std::vector<uint16_t>{}));

    auto result = sut->getStatus();

    EXPECT_FALSE(result.has_value());
}

TEST_F(WVSTest, getInfoReadsInfoRegisterBlock) {
    std::vector<uint16_t> registers(24, 0);

    registers[0] = 1;        // registerFormatVersion
    registers[1] = 0x1111;   // uniqueIdentifier[0]
    registers[2] = 0x2222;
    registers[3] = 0x3333;
    registers[4] = 0x4444;
    registers[5] = 0x5555;
    registers[6] = 0x6666;
    registers[7] = 0x7777;
    registers[8] = 0x8888;

    registers[9]  = 1; // mc major
    registers[10] = 2; // mc minor
    registers[11] = 3; // mc patch

    EXPECT_CALL(*mock, readHoldingRegister(0x0000, 24))
        .WillOnce(Return(registers));

    auto result = sut->getInfo();

    ASSERT_TRUE(result.has_value());
    EXPECT_EQ(result->registerFormatVersion, 1);
    EXPECT_EQ(result->mcSoftwareVersion, "v1.2.3");
}

} // namespace














#include "ModbusASCII.hpp"

#include <algorithm>
#include <charconv>
#include <cstdint>
#include <cstring>
#include <limits>
#include <optional>
#include <vector>

#include "DebugInterface/Write.hpp"

namespace HAL::Implementation::HLDriver {

static constexpr char START_CHAR{':'};
static constexpr char CARRIAGE_RETURN{'\r'};
static constexpr char LINE_FEED{'\n'};

static constexpr size_t SIZE_START{1};
static constexpr size_t SIZE_ADDRESS{2};
static constexpr size_t SIZE_FUNCTION{2};
static constexpr size_t SIZE_LRC{2};
static constexpr size_t SIZE_END{2};

static constexpr size_t SIZE_PREFIX{SIZE_START + SIZE_ADDRESS + SIZE_FUNCTION};
static constexpr size_t SIZE_SUFFIX{SIZE_LRC + SIZE_END};
static constexpr size_t SIZE_MSG_FRAME{SIZE_PREFIX + SIZE_SUFFIX};

static constexpr size_t BYTES_TO_STRING_FACTOR{2};

namespace MsgBuilder {

static constexpr size_t MAX_REGISTER{125};
static constexpr char HEX[]{"0123456789ABCDEF"};

static void appendHexByte(uint8_t value, std::vector<uint8_t>& out) {
    out.push_back(static_cast<uint8_t>(HEX[(value >> 4) & 0x0F]));
    out.push_back(static_cast<uint8_t>(HEX[value & 0x0F]));
}

static void appendU16(uint16_t value, std::vector<uint8_t>& out) {
    appendHexByte(static_cast<uint8_t>((value >> 8) & 0xFF), out);
    appendHexByte(static_cast<uint8_t>(value & 0xFF), out);
}

} // namespace MsgBuilder

namespace MsgExtractor {

static constexpr size_t SLAVE_ADDRESS_INDEX{1};
static constexpr size_t FUNCTION_INDEX{3};
static constexpr size_t BYTE_COUNT_SIZE{7};
static constexpr size_t BYTE_COUNT_INDEX{BYTE_COUNT_SIZE - 2U};

static std::optional<uint8_t> fromString(const std::vector<uint8_t>& msg, size_t index) {
    if (index + 1 >= msg.size()) {
        return std::nullopt;
    }

    const char* start{reinterpret_cast<const char*>(&msg[index])};
    const char* end{start + 2};

    uint8_t result{};
    auto [ptr, ec] = std::from_chars(start, end, result, 16);

    if (ptr != end || ec != std::errc{}) {
        return std::nullopt;
    }

    return result;
}

static bool hasEvenSize(const std::vector<uint8_t>& msg) {
    return (msg.size() % 2U) == 0U;
}

static std::vector<uint8_t> extractLRCBytes(const std::vector<uint8_t>& msg) {
    if (hasEvenSize(msg)) {
        return {};
    }

    if (msg.size() < SIZE_MSG_FRAME) {
        return {};
    }

    std::vector<uint8_t> retval;
    retval.reserve(msg.size() / BYTES_TO_STRING_FACTOR);

    // Skip ':' and decode until before CRLF.
    // This includes: address, function, payload, LRC.
    for (size_t index = SIZE_START; index + 1U < msg.size() - SIZE_END; index += 2U) {
        auto byte = fromString(msg, index);
        if (!byte.has_value()) {
            return {};
        }

        retval.push_back(byte.value());
    }

    return retval;
}

} // namespace MsgExtractor

ModbusASCII::ModbusASCII(
    std::shared_ptr<HAL::Interfaces::LLDriver::IUART> uart,
    uint8_t slaveAddress)
    : m_uart{uart}
    , m_slaveAddress{slaveAddress} {
}

std::vector<uint16_t> ModbusASCII::readHoldingRegister(
    uint16_t registerAddress,
    uint16_t quantity) {
    sendMessage(buildReadMessage(registerAddress, quantity));

    const auto receivedMessage = receiveMessage();
    const auto lrcBytes = MsgExtractor::extractLRCBytes(receivedMessage);

    if (!isReadResultValid(receivedMessage, lrcBytes)) {
        return {};
    }

    const auto data = extractData(lrcBytes);

    std::vector<uint16_t> retval;
    retval.reserve(data.size() / sizeof(uint16_t));

    for (size_t index = 0; index + 1U < data.size(); index += 2U) {
        retval.push_back(static_cast<uint16_t>(
            static_cast<uint16_t>(data[index]) << 8U |
            static_cast<uint16_t>(data[index + 1U])));
    }

    return retval;
}

bool ModbusASCII::writeRegister(
    uint16_t registerAddress,
    const std::vector<uint16_t>& values) {
    sendMessage(buildWriteMessage(registerAddress, values));

    const auto receivedMessage = receiveMessage();
    const auto lrcBytes = MsgExtractor::extractLRCBytes(receivedMessage);

    return isWriteResultValid(receivedMessage, lrcBytes);
}

uint8_t ModbusASCII::calcLRC(const std::vector<uint8_t>& data) const {
    uint8_t retval{0};

    for (auto byte : data) {
        retval = static_cast<uint8_t>(retval + byte);
    }

    return static_cast<uint8_t>(-static_cast<int32_t>(retval));
}

void ModbusASCII::insertLRC(
    uint8_t fc,
    const std::vector<uint8_t>& data,
    std::vector<uint8_t>& retval) const {
    std::vector<uint8_t> lrcBytes;
    lrcBytes.reserve(sizeof(m_slaveAddress) + sizeof(fc) + data.size());

    lrcBytes.push_back(m_slaveAddress);
    lrcBytes.push_back(fc);
    lrcBytes.insert(lrcBytes.end(), data.begin(), data.end());

    MsgBuilder::appendHexByte(calcLRC(lrcBytes), retval);
}

std::vector<uint8_t> ModbusASCII::build(
    const ModbusASCII::FunctionCode& functionCode,
    const std::vector<uint8_t>& data) const {
    sysassert(m_slaveAddress > 0 && m_slaveAddress < 248);

    const auto fc = static_cast<uint8_t>(functionCode);

    std::vector<uint8_t> retval;
    retval.reserve(SIZE_MSG_FRAME + data.size() * BYTES_TO_STRING_FACTOR);

    retval.push_back(static_cast<uint8_t>(START_CHAR));

    MsgBuilder::appendHexByte(m_slaveAddress, retval);
    MsgBuilder::appendHexByte(fc, retval);

    for (auto byte : data) {
        MsgBuilder::appendHexByte(byte, retval);
    }

    insertLRC(fc, data, retval);

    retval.push_back(static_cast<uint8_t>(CARRIAGE_RETURN));
    retval.push_back(static_cast<uint8_t>(LINE_FEED));

    return retval;
}

std::vector<uint8_t> ModbusASCII::buildReadMessage(
    uint16_t registerAddress,
    uint16_t quantity) const {
    sysassert(quantity > 0);
    sysassert(quantity < MsgBuilder::MAX_REGISTER);

    std::vector<uint8_t> data;
    data.reserve(sizeof(registerAddress) + sizeof(quantity));

    MsgBuilder::appendU16(registerAddress, data);
    MsgBuilder::appendU16(quantity, data);

    return build(FunctionCode::READ_HOLDING_REGISTERS, data);
}

std::vector<uint8_t> ModbusASCII::buildWriteMessage(
    uint16_t registerAddress,
    const std::vector<uint16_t>& values,
    uint16_t quantity) const {
    sysassert(!values.empty());
    sysassert(values.size() < MsgBuilder::MAX_REGISTER);

    quantity = quantity == 0U
        ? static_cast<uint16_t>(values.size())
        : quantity;

    const auto byteCount = static_cast<uint8_t>(values.size() * sizeof(uint16_t));

    std::vector<uint8_t> data;
    data.reserve(
        sizeof(registerAddress) +
        sizeof(quantity) +
        sizeof(byteCount) +
        values.size() * sizeof(uint16_t));

    MsgBuilder::appendU16(registerAddress, data);
    MsgBuilder::appendU16(quantity, data);
    data.push_back(byteCount);

    for (auto value : values) {
        MsgBuilder::appendU16(value, data);
    }

    return build(FunctionCode::WRITE_MULTIPLE_REGISTERS, data);
}

bool ModbusASCII::isMsgFrameAndLRCValid(
    const std::vector<uint8_t>& msg,
    const std::vector<uint8_t>& lrcBytes,
    const ModbusASCII::FunctionCode& functionCode) const {
    if (msg.size() < SIZE_MSG_FRAME) {
        return false;
    }

    if (msg.front() != static_cast<uint8_t>(START_CHAR)) {
        return false;
    }

    if (msg[msg.size() - 2U] != static_cast<uint8_t>(CARRIAGE_RETURN)) {
        return false;
    }

    if (msg[msg.size() - 1U] != static_cast<uint8_t>(LINE_FEED)) {
        return false;
    }

    if (lrcBytes.size() < 3U) {
        return false;
    }

    if (lrcBytes.front() != m_slaveAddress) {
        return false;
    }

    if (lrcBytes[1] != static_cast<uint8_t>(functionCode)) {
        return false;
    }

    const auto expectedLRC = lrcBytes.back();

    std::vector<uint8_t> dataForLRC;
    dataForLRC.reserve(lrcBytes.size() - 1U);
    dataForLRC.insert(dataForLRC.end(), lrcBytes.begin(), lrcBytes.end() - 1);

    return expectedLRC == calcLRC(dataForLRC);
}

bool ModbusASCII::isReadResultComplete(const std::vector<uint8_t>& msg) const {
    const auto msgSize = msg.size();

    if (MsgExtractor::hasEvenSize(msg)) {
        return false;
    }

    if (msgSize <= MsgExtractor::BYTE_COUNT_SIZE) {
        return false;
    }

    const auto byteCount = MsgExtractor::fromString(msg, MsgExtractor::BYTE_COUNT_INDEX);
    if (!byteCount.has_value()) {
        return false;
    }

    const auto expectedSize =
        MsgExtractor::BYTE_COUNT_SIZE +
        byteCount.value() * BYTES_TO_STRING_FACTOR +
        SIZE_SUFFIX;

    return msgSize == expectedSize;
}

bool ModbusASCII::isReadResultValid(
    const std::vector<uint8_t>& msg,
    const std::vector<uint8_t>& lrcBytes) const {
    return isReadResultComplete(msg) &&
           isMsgFrameAndLRCValid(
               msg,
               lrcBytes,
               ModbusASCII::FunctionCode::READ_HOLDING_REGISTERS);
}

bool ModbusASCII::isWriteResultValid(
    const std::vector<uint8_t>& msg,
    const std::vector<uint8_t>& lrcBytes) const {
    static constexpr auto EXPECTED_LENGTH{17};

    return msg.size() == EXPECTED_LENGTH &&
           isMsgFrameAndLRCValid(
               msg,
               lrcBytes,
               ModbusASCII::FunctionCode::WRITE_MULTIPLE_REGISTERS);
}

std::vector<uint8_t> ModbusASCII::extractData(
    const std::vector<uint8_t>& lrcBytes) const {
    // Read response decoded frame:
    // [slaveAddress, functionCode, byteCount, data..., lrc]
    if (lrcBytes.size() <= 4U) {
        return {};
    }

    return std::vector<uint8_t>{lrcBytes.begin() + 3, lrcBytes.end() - 1};
}

void ModbusASCII::sendMessage(const std::vector<uint8_t>& msg) const {
    m_uart->flushInput();
    m_uart->write(msg);

    if (!m_uart->waitForBytesWritten(TIMEOUT_VAL)) {
        PANIC_MODE();
    }
}

std::vector<uint8_t> ModbusASCII::receiveMessage() const {
    std::vector<uint8_t> receivedMessage;

    ::Utilities::ElapsedTimer timer;

    while (true) {
        if (receivedMessage.size() >= SIZE_END &&
            receivedMessage[receivedMessage.size() - 2U] == static_cast<uint8_t>(CARRIAGE_RETURN) &&
            receivedMessage[receivedMessage.size() - 1U] == static_cast<uint8_t>(LINE_FEED)) {
            return receivedMessage;
        }

        if (timer.isExpired(TIMEOUT_VAL)) {
            SERIAL_DEBUG_LEVEL_WARNING(
                "%s: No complete message received!",
                __PRETTY_FUNCTION__);

            return {};
        }

        const auto elapsed = timer.elapsed();
        const auto timeRemaining = TIMEOUT_VAL - std::min(elapsed, TIMEOUT_VAL);

        if (m_uart->waitForReadyRead(timeRemaining)) {
            auto read = m_uart->read();
            receivedMessage.insert(receivedMessage.end(), read.begin(), read.end());

            if (read.empty()) {
                (void)m_uart->waitForReadyRead(10_milliseconds);
            }
        }
    }
}

} // namespace HAL::Implementation::HLDriver













#include "ModbusASCII.hpp"

#include <algorithm>
#include <charconv>
#include <chrono>
#include <cstdint>
#include <optional>
#include <vector>

#include "DebugInterface/Write.hpp"

namespace HAL::Implementation::HLDriver {

static constexpr uint8_t START_CHAR{':'};
static constexpr uint8_t CARRIAGE_RETURN{'\r'};
static constexpr uint8_t LINE_FEED{'\n'};

static constexpr size_t SIZE_START{1U};
static constexpr size_t SIZE_ADDRESS{2U};
static constexpr size_t SIZE_FUNCTION{2U};
static constexpr size_t SIZE_LRC{2U};
static constexpr size_t SIZE_END{2U};

static constexpr size_t SIZE_PREFIX{SIZE_START + SIZE_ADDRESS + SIZE_FUNCTION};
static constexpr size_t SIZE_SUFFIX{SIZE_LRC + SIZE_END};
static constexpr size_t SIZE_MSG_FRAME{SIZE_PREFIX + SIZE_SUFFIX};

static constexpr size_t BYTES_TO_STRING_FACTOR{2U};

static constexpr uint32_t BITS_PER_BYTE{10U}; // 8N1: 1 start + 8 data + 1 stop
static constexpr uint32_t BAUD_RATE{9600U};
static constexpr auto RX_DELAY_MARGIN{2_milliseconds};

namespace MsgBuilder {

static constexpr size_t MAX_REGISTER{125U};
static constexpr char HEX[]{"0123456789ABCDEF"};

static void appendHexByte(uint8_t value, std::vector<uint8_t>& out) {
    out.push_back(static_cast<uint8_t>(HEX[(value >> 4U) & 0x0FU]));
    out.push_back(static_cast<uint8_t>(HEX[value & 0x0FU]));
}

static void appendU16(uint16_t value, std::vector<uint8_t>& out) {
    appendHexByte(static_cast<uint8_t>((value >> 8U) & 0xFFU), out);
    appendHexByte(static_cast<uint8_t>(value & 0xFFU), out);
}

} // namespace MsgBuilder

namespace MsgExtractor {

static constexpr size_t BYTE_COUNT_INDEX{5U};

static bool hasEvenSize(const std::vector<uint8_t>& msg) {
    return (msg.size() % 2U) == 0U;
}

static std::optional<uint8_t> fromString(
    const std::vector<uint8_t>& msg,
    size_t index)
{
    if (index + 1U >= msg.size()) {
        return std::nullopt;
    }

    const char* begin{reinterpret_cast<const char*>(&msg[index])};
    const char* end{begin + 2};

    uint8_t value{};
    const auto [ptr, ec] = std::from_chars(begin, end, value, 16);

    if (ptr != end || ec != std::errc{}) {
        return std::nullopt;
    }

    return value;
}

static std::vector<uint8_t> decodeAsciiFrame(const std::vector<uint8_t>& msg) {
    if (msg.size() < SIZE_MSG_FRAME) {
        return {};
    }

    if (hasEvenSize(msg)) {
        return {};
    }

    std::vector<uint8_t> decoded;
    decoded.reserve(msg.size() / BYTES_TO_STRING_FACTOR);

    // Skip ':' and decode all ASCII hex bytes until before CRLF.
    // Result: [slaveAddress, functionCode, payload..., lrc]
    for (size_t index = SIZE_START;
         index + 1U < msg.size() - SIZE_END;
         index += BYTES_TO_STRING_FACTOR) {
        const auto byte = fromString(msg, index);
        if (!byte.has_value()) {
            return {};
        }

        decoded.push_back(byte.value());
    }

    return decoded;
}

} // namespace MsgExtractor

ModbusASCII::ModbusASCII(
    std::shared_ptr<HAL::Interfaces::LLDriver::IUART> uart,
    uint8_t slaveAddress)
    : m_uart{uart}
    , m_slaveAddress{slaveAddress}
{
}

std::vector<uint16_t> ModbusASCII::readHoldingRegister(
    uint16_t registerAddress,
    uint16_t quantity)
{
    const auto request = buildReadMessage(registerAddress, quantity);

    sendMessage(request);
    waitInitialRxDelay(request.size(), expectedReadResponseSize(quantity));

    const auto receivedMessage = receiveMessage();

    const auto decoded = validateAndDecode(
        receivedMessage,
        FunctionCode::READ_HOLDING_REGISTERS);

    if (!decoded.has_value()) {
        return {};
    }

    const auto data = extractReadData(decoded.value());
    if (data.size() != quantity * sizeof(uint16_t)) {
        return {};
    }

    std::vector<uint16_t> registers;
    registers.reserve(quantity);

    for (size_t index = 0U; index + 1U < data.size(); index += 2U) {
        registers.push_back(static_cast<uint16_t>(
            static_cast<uint16_t>(data[index]) << 8U |
            static_cast<uint16_t>(data[index + 1U])));
    }

    return registers;
}

bool ModbusASCII::writeRegister(
    uint16_t registerAddress,
    const std::vector<uint16_t>& values)
{
    const auto request = buildWriteMessage(registerAddress, values);

    sendMessage(request);
    waitInitialRxDelay(request.size(), expectedWriteResponseSize());

    const auto receivedMessage = receiveMessage();

    return validateAndDecode(
        receivedMessage,
        FunctionCode::WRITE_MULTIPLE_REGISTERS).has_value();
}

std::vector<uint8_t> ModbusASCII::buildReadMessage(
    uint16_t registerAddress,
    uint16_t quantity) const
{
    sysassert(quantity > 0U);
    sysassert(quantity < MsgBuilder::MAX_REGISTER);

    std::vector<uint8_t> data;
    data.reserve(sizeof(registerAddress) + sizeof(quantity));

    MsgBuilder::appendU16(registerAddress, data);
    MsgBuilder::appendU16(quantity, data);

    return build(FunctionCode::READ_HOLDING_REGISTERS, data);
}

std::vector<uint8_t> ModbusASCII::buildWriteMessage(
    uint16_t registerAddress,
    const std::vector<uint16_t>& values,
    uint16_t quantity) const
{
    sysassert(!values.empty());
    sysassert(values.size() < MsgBuilder::MAX_REGISTER);

    const auto registerCount = quantity == 0U
        ? static_cast<uint16_t>(values.size())
        : quantity;

    const auto byteCount = static_cast<uint8_t>(
        values.size() * sizeof(uint16_t));

    std::vector<uint8_t> data;
    data.reserve(
        sizeof(registerAddress) +
        sizeof(registerCount) +
        sizeof(byteCount) +
        values.size() * sizeof(uint16_t));

    MsgBuilder::appendU16(registerAddress, data);
    MsgBuilder::appendU16(registerCount, data);
    data.push_back(byteCount);

    for (const auto value : values) {
        MsgBuilder::appendU16(value, data);
    }

    return build(FunctionCode::WRITE_MULTIPLE_REGISTERS, data);
}

std::vector<uint8_t> ModbusASCII::build(
    const ModbusASCII::FunctionCode& functionCode,
    const std::vector<uint8_t>& data) const
{
    sysassert(m_slaveAddress > 0U && m_slaveAddress < 248U);

    const auto function = static_cast<uint8_t>(functionCode);

    std::vector<uint8_t> message;
    message.reserve(SIZE_MSG_FRAME + data.size() * BYTES_TO_STRING_FACTOR);

    message.push_back(START_CHAR);

    MsgBuilder::appendHexByte(m_slaveAddress, message);
    MsgBuilder::appendHexByte(function, message);

    for (const auto byte : data) {
        MsgBuilder::appendHexByte(byte, message);
    }

    appendLRC(function, data, message);

    message.push_back(CARRIAGE_RETURN);
    message.push_back(LINE_FEED);

    return message;
}

void ModbusASCII::appendLRC(
    uint8_t functionCode,
    const std::vector<uint8_t>& data,
    std::vector<uint8_t>& message) const
{
    std::vector<uint8_t> lrcInput;
    lrcInput.reserve(2U + data.size());

    lrcInput.push_back(m_slaveAddress);
    lrcInput.push_back(functionCode);
    lrcInput.insert(lrcInput.end(), data.begin(), data.end());

    MsgBuilder::appendHexByte(calcLRC(lrcInput), message);
}

uint8_t ModbusASCII::calcLRC(const std::vector<uint8_t>& data) const {
    uint8_t sum{0U};

    for (const auto byte : data) {
        sum = static_cast<uint8_t>(sum + byte);
    }

    return static_cast<uint8_t>(-static_cast<int32_t>(sum));
}

std::optional<std::vector<uint8_t>> ModbusASCII::validateAndDecode(
    const std::vector<uint8_t>& msg,
    const ModbusASCII::FunctionCode& functionCode) const
{
    if (msg.size() < SIZE_MSG_FRAME) {
        return std::nullopt;
    }

    if (msg.front() != START_CHAR) {
        return std::nullopt;
    }

    if (msg[msg.size() - 2U] != CARRIAGE_RETURN) {
        return std::nullopt;
    }

    if (msg[msg.size() - 1U] != LINE_FEED) {
        return std::nullopt;
    }

    auto decoded = MsgExtractor::decodeAsciiFrame(msg);
    if (decoded.size() < 3U) {
        return std::nullopt;
    }

    if (decoded[0U] != m_slaveAddress) {
        return std::nullopt;
    }

    if (decoded[1U] != static_cast<uint8_t>(functionCode)) {
        return std::nullopt;
    }

    const auto receivedLRC = decoded.back();

    std::vector<uint8_t> lrcInput;
    lrcInput.reserve(decoded.size() - 1U);
    lrcInput.insert(lrcInput.end(), decoded.begin(), decoded.end() - 1);

    if (receivedLRC != calcLRC(lrcInput)) {
        return std::nullopt;
    }

    if (functionCode == FunctionCode::READ_HOLDING_REGISTERS &&
        !isDecodedReadResponseComplete(decoded)) {
        return std::nullopt;
    }

    if (functionCode == FunctionCode::WRITE_MULTIPLE_REGISTERS &&
        !isDecodedWriteResponseComplete(decoded)) {
        return std::nullopt;
    }

    return decoded;
}

bool ModbusASCII::isDecodedReadResponseComplete(
    const std::vector<uint8_t>& decoded) const
{
    // [slaveAddress, functionCode, byteCount, data..., lrc]
    if (decoded.size() < 5U) {
        return false;
    }

    const auto byteCount = decoded[2U];
    const auto expectedSize =
        1U + // slave address
        1U + // function code
        1U + // byte count
        byteCount +
        1U;  // lrc

    return decoded.size() == expectedSize;
}

bool ModbusASCII::isDecodedWriteResponseComplete(
    const std::vector<uint8_t>& decoded) const
{
    // [slaveAddress, functionCode, registerAddressHi, registerAddressLo,
    //  quantityHi, quantityLo, lrc]
    static constexpr size_t EXPECTED_SIZE{7U};

    return decoded.size() == EXPECTED_SIZE;
}

std::vector<uint8_t> ModbusASCII::extractReadData(
    const std::vector<uint8_t>& decoded) const
{
    // Read response:
    // [slaveAddress, functionCode, byteCount, data..., lrc]
    if (!isDecodedReadResponseComplete(decoded)) {
        return {};
    }

    return std::vector<uint8_t>{decoded.begin() + 3, decoded.end() - 1};
}

size_t ModbusASCII::expectedReadResponseSize(uint16_t quantity) const {
    return SIZE_START +
           SIZE_ADDRESS +
           SIZE_FUNCTION +
           2U + // byte count, ASCII encoded
           quantity * sizeof(uint16_t) * BYTES_TO_STRING_FACTOR +
           SIZE_LRC +
           SIZE_END;
}

size_t ModbusASCII::expectedWriteResponseSize() const {
    return SIZE_START +
           SIZE_ADDRESS +
           SIZE_FUNCTION +
           4U + // register address, ASCII encoded
           4U + // quantity, ASCII encoded
           SIZE_LRC +
           SIZE_END;
}

std::chrono::milliseconds ModbusASCII::calculateTransferTime(
    size_t txSize,
    size_t rxSize,
    uint32_t baudRate) const
{
    const auto totalBits =
        static_cast<uint64_t>(txSize + rxSize) * BITS_PER_BYTE;

    const auto microseconds =
        (totalBits * 1'000'000ULL + baudRate - 1U) / baudRate;

    return std::chrono::duration_cast<std::chrono::milliseconds>(
        std::chrono::microseconds{microseconds});
}

void ModbusASCII::waitInitialRxDelay(
    size_t txSize,
    size_t rxSize) const
{
    const auto delay =
        calculateTransferTime(txSize, rxSize, BAUD_RATE) + RX_DELAY_MARGIN;

    (void)m_uart->waitForReadyRead(delay);
}

void ModbusASCII::sendMessage(const std::vector<uint8_t>& msg) const {
    m_uart->flushInput();
    m_uart->write(msg);

    if (!m_uart->waitForBytesWritten(TIMEOUT_VAL)) {
        PANIC_MODE();
    }
}

std::vector<uint8_t> ModbusASCII::receiveMessage() const {
    std::vector<uint8_t> receivedMessage;

    ::Utilities::ElapsedTimer timer;

    while (!timer.isExpired(TIMEOUT_VAL)) {
        const auto remaining =
            TIMEOUT_VAL - std::min(timer.elapsed(), TIMEOUT_VAL);

        if (!m_uart->waitForReadyRead(remaining)) {
            break;
        }

        auto chunk = m_uart->read();
        receivedMessage.insert(
            receivedMessage.end(),
            chunk.begin(),
            chunk.end());

        if (receivedMessage.size() >= SIZE_END &&
            receivedMessage[receivedMessage.size() - 2U] == CARRIAGE_RETURN &&
            receivedMessage[receivedMessage.size() - 1U] == LINE_FEED) {
            return receivedMessage;
        }
    }

    SERIAL_DEBUG_LEVEL_WARNING(
        "%s: No complete message received!",
        __PRETTY_FUNCTION__);

    return {};
}

} // namespace HAL::Implementation::HLDriver
