export interface ClaudeSettings {
  path: string;
  custom_path: string | null;
  max_concurrent: number;
}

export interface CodexSettings {
  max_concurrent: number;
}

export interface IndexSettings {
  enabled: boolean;
  auto_update: boolean;
}

export interface TranslationSettings {
  model_downloaded: boolean;
  model_path: string | null;
  cache_enabled: boolean;
}

export interface DatabaseSettings {
  db_type: string;
  connection_string: string | null;
}

export interface UiSettings {
  theme: string;
  language: string;
}

export interface ViewerSettings {
  version: number;
  port: number;
  claude: ClaudeSettings;
  codex: CodexSettings;
  index: IndexSettings;
  translation: TranslationSettings;
  database: DatabaseSettings;
  ui: UiSettings;
}

export interface ConcurrencyStatus {
  cc_running: number;
  cx_running: number;
  cc_max: number;
  cx_max: number;
  /** CC 队列中等待的任务数 */
  cc_queued: number;
  /** CX 队列中等待的任务数 */
  cx_queued: number;
  /** 总运行数 */
  total_running: number;
  /** 总并发限制 */
  total_max: number;
}

