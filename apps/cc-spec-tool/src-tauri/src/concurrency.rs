// concurrency.rs - 增强版并发控制器
//
// 功能:
// - 任务队列 (VecDeque)
// - 生命周期管理
// - 自动调度和回调通知
// - CC/CX 分开计数但共享总上限

use serde::{Deserialize, Serialize};
use std::collections::VecDeque;
use std::sync::atomic::{AtomicU64, AtomicU8, Ordering};
use std::sync::{Arc, Mutex};
use tokio::sync::oneshot;

/// 总并发限制（CC + CX 共享）
pub const TOTAL_CONCURRENCY_LIMIT: u8 = 6;

/// 任务类型
#[derive(Clone, Debug, Serialize, Deserialize, PartialEq)]
pub enum TaskType {
    CC,
    CX,
}

/// 待执行任务
pub struct PendingTask {
    /// 任务 ID
    pub id: u64,
    /// 任务类型
    pub task_type: TaskType,
    /// 任务描述（用于前端展示）
    pub description: String,
    /// 项目路径
    pub project_path: String,
    /// 排队时间
    pub queued_at: chrono::DateTime<chrono::Utc>,
    /// 任务就绪通知
    tx: Option<oneshot::Sender<TaskHandle>>,
}

/// 任务句柄，用于释放资源
pub struct TaskHandle {
    task_id: u64,
    task_type: TaskType,
    controller: Arc<ConcurrencyController>,
}

impl TaskHandle {
    /// 释放任务资源
    pub fn release(self) {
        match self.task_type {
            TaskType::CC => self.controller.release_cc_internal(),
            TaskType::CX => self.controller.release_cx_internal(),
        }
        // 尝试调度下一个排队任务
        self.controller.try_schedule_next();
    }
}

impl Drop for TaskHandle {
    fn drop(&mut self) {
        // Drop 时自动释放（如果尚未手动释放）
        // 注意：这里不做任何事，因为 release() 会消耗 self
    }
}

/// 队列中任务信息（序列化版本）
#[derive(Clone, Debug, Serialize)]
pub struct QueuedTaskInfo {
    pub id: u64,
    pub task_type: String,
    pub description: String,
    pub project_path: String,
    pub queued_at: String,
    pub position: usize,
}

/// 并发状态
#[derive(Clone, Debug, Serialize)]
pub struct ConcurrencyStatus {
    pub cc_running: u8,
    pub cx_running: u8,
    pub cc_max: u8,
    pub cx_max: u8,
    pub cc_queued: usize,
    pub cx_queued: usize,
    pub total_running: u8,
    pub total_max: u8,
    pub queue: Vec<QueuedTaskInfo>,
}

/// 并发控制器
pub struct ConcurrencyController {
    /// CC 运行中计数
    cc_running: AtomicU8,
    /// CX 运行中计数
    cx_running: AtomicU8,
    /// CC 最大并发
    cc_max: AtomicU8,
    /// CX 最大并发
    cx_max: AtomicU8,
    /// 任务 ID 计数器
    task_id_counter: AtomicU64,
    /// 任务队列
    queue: Mutex<VecDeque<PendingTask>>,
}

impl ConcurrencyController {
    pub fn new(cc_max: u8, cx_max: u8) -> Self {
        Self {
            cc_running: AtomicU8::new(0),
            cx_running: AtomicU8::new(0),
            cc_max: AtomicU8::new(cc_max),
            cx_max: AtomicU8::new(cx_max),
            task_id_counter: AtomicU64::new(0),
            queue: Mutex::new(VecDeque::new()),
        }
    }

    /// 更新最大并发限制
    pub fn set_limits(&self, cc_max: u8, cx_max: u8) {
        self.cc_max.store(cc_max, Ordering::SeqCst);
        self.cx_max.store(cx_max, Ordering::SeqCst);
    }

    /// 获取当前总运行数
    pub fn total_running(&self) -> u8 {
        self.cc_running.load(Ordering::SeqCst) + self.cx_running.load(Ordering::SeqCst)
    }

    /// 检查是否可以启动 CC
    fn can_start_cc(&self) -> bool {
        self.cc_running.load(Ordering::SeqCst) < self.cc_max.load(Ordering::SeqCst)
            && self.total_running() < TOTAL_CONCURRENCY_LIMIT
    }

    /// 检查是否可以启动 CX
    fn can_start_cx(&self) -> bool {
        self.cx_running.load(Ordering::SeqCst) < self.cx_max.load(Ordering::SeqCst)
            && self.total_running() < TOTAL_CONCURRENCY_LIMIT
    }

    /// 内部 CC 计数增加
    fn acquire_cc_internal(&self) {
        self.cc_running.fetch_add(1, Ordering::SeqCst);
    }

    /// 内部 CX 计数增加
    fn acquire_cx_internal(&self) {
        self.cx_running.fetch_add(1, Ordering::SeqCst);
    }

    /// 内部 CC 计数减少
    fn release_cc_internal(&self) {
        let prev = self.cc_running.fetch_sub(1, Ordering::SeqCst);
        if prev == 0 {
            self.cc_running.store(0, Ordering::SeqCst);
        }
    }

    /// 内部 CX 计数减少
    fn release_cx_internal(&self) {
        let prev = self.cx_running.fetch_sub(1, Ordering::SeqCst);
        if prev == 0 {
            self.cx_running.store(0, Ordering::SeqCst);
        }
    }

    /// 生成任务 ID
    fn next_task_id(&self) -> u64 {
        self.task_id_counter.fetch_add(1, Ordering::SeqCst)
    }

    /// 尝试立即获取 CC 资源，失败则排队
    pub fn try_acquire_cc(
        self: &Arc<Self>,
        description: String,
        project_path: String,
    ) -> Result<TaskHandle, oneshot::Receiver<TaskHandle>> {
        if self.can_start_cc() {
            self.acquire_cc_internal();
            let handle = TaskHandle {
                task_id: self.next_task_id(),
                task_type: TaskType::CC,
                controller: Arc::clone(self),
            };
            Ok(handle)
        } else {
            let (tx, rx) = oneshot::channel();
            let task = PendingTask {
                id: self.next_task_id(),
                task_type: TaskType::CC,
                description,
                project_path,
                queued_at: chrono::Utc::now(),
                tx: Some(tx),
            };
            self.queue.lock().unwrap().push_back(task);
            Err(rx)
        }
    }

    /// 尝试立即获取 CX 资源，失败则排队
    pub fn try_acquire_cx(
        self: &Arc<Self>,
        description: String,
        project_path: String,
    ) -> Result<TaskHandle, oneshot::Receiver<TaskHandle>> {
        if self.can_start_cx() {
            self.acquire_cx_internal();
            let handle = TaskHandle {
                task_id: self.next_task_id(),
                task_type: TaskType::CX,
                controller: Arc::clone(self),
            };
            Ok(handle)
        } else {
            let (tx, rx) = oneshot::channel();
            let task = PendingTask {
                id: self.next_task_id(),
                task_type: TaskType::CX,
                description,
                project_path,
                queued_at: chrono::Utc::now(),
                tx: Some(tx),
            };
            self.queue.lock().unwrap().push_back(task);
            Err(rx)
        }
    }

    /// 尝试调度下一个排队任务
    fn try_schedule_next(self: &Arc<Self>) {
        let mut queue = self.queue.lock().unwrap();
        
        // 找到第一个可以执行的任务
        let mut i = 0;
        while i < queue.len() {
            let can_run = match queue[i].task_type {
                TaskType::CC => self.can_start_cc(),
                TaskType::CX => self.can_start_cx(),
            };
            
            if can_run {
                // 移除并执行任务
                if let Some(mut task) = queue.remove(i) {
                    match task.task_type {
                        TaskType::CC => self.acquire_cc_internal(),
                        TaskType::CX => self.acquire_cx_internal(),
                    }
                    let handle = TaskHandle {
                        task_id: task.id,
                        task_type: task.task_type.clone(),
                        controller: Arc::clone(self),
                    };
                    if let Some(tx) = task.tx.take() {
                        let _ = tx.send(handle);
                    }
                }
                // 只调度一个任务
                break;
            } else {
                i += 1;
            }
        }
    }

    /// 从队列中移除任务（取消排队）
    pub fn cancel_queued(&self, task_id: u64) -> bool {
        let mut queue = self.queue.lock().unwrap();
        if let Some(pos) = queue.iter().position(|t| t.id == task_id) {
            queue.remove(pos);
            true
        } else {
            false
        }
    }

    /// 获取当前状态
    pub fn status(&self) -> ConcurrencyStatus {
        let queue = self.queue.lock().unwrap();
        let cc_queued = queue.iter().filter(|t| t.task_type == TaskType::CC).count();
        let cx_queued = queue.iter().filter(|t| t.task_type == TaskType::CX).count();
        
        let queue_info: Vec<QueuedTaskInfo> = queue
            .iter()
            .enumerate()
            .map(|(pos, t)| QueuedTaskInfo {
                id: t.id,
                task_type: match t.task_type {
                    TaskType::CC => "CC".to_string(),
                    TaskType::CX => "CX".to_string(),
                },
                description: t.description.clone(),
                project_path: t.project_path.clone(),
                queued_at: t.queued_at.to_rfc3339(),
                position: pos,
            })
            .collect();

        ConcurrencyStatus {
            cc_running: self.cc_running.load(Ordering::SeqCst),
            cx_running: self.cx_running.load(Ordering::SeqCst),
            cc_max: self.cc_max.load(Ordering::SeqCst),
            cx_max: self.cx_max.load(Ordering::SeqCst),
            cc_queued,
            cx_queued,
            total_running: self.total_running(),
            total_max: TOTAL_CONCURRENCY_LIMIT,
            queue: queue_info,
        }
    }

    /// 获取 CC 运行数
    pub fn cc_running(&self) -> u8 {
        self.cc_running.load(Ordering::SeqCst)
    }

    /// 获取 CX 运行数
    pub fn cx_running(&self) -> u8 {
        self.cx_running.load(Ordering::SeqCst)
    }
}

impl Default for ConcurrencyController {
    fn default() -> Self {
        Self::new(3, 5)
    }
}
