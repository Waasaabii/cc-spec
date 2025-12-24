export type TranslationModelFileStatus = {
    name: string;
    exists: boolean;
    size: number | null;
};

export type TranslationModelStatus = {
    downloaded: boolean;
    model_path: string | null;
    model_size: number | null;
    model_version: string | null;
    files: TranslationModelFileStatus[];
    ready: boolean;
    loaded: boolean;
};

export type TranslationDownloadProgress = {
    progress: number;
    message: string;
    current_file?: string;
    file_index?: number;
    total_files?: number;
};

export type TranslationDownloadCompleted = {
    success: boolean;
    error?: string;
    path?: string;
    total_size?: number;
};

export type TranslationCacheStats = {
    cached_count: number;
    model_ready: boolean;
    model_loaded: boolean;
};
