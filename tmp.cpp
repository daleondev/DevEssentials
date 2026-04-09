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
