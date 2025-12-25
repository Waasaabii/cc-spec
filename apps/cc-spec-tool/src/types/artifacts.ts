export type ArtifactRoot = {
    id: string;
    label: string;
    kind: "dir" | "file";
    exists: boolean;
    relPath: string;
    absPath: string;
};

export type ArtifactEntry = {
    name: string;
    kind: "dir" | "file";
    relPath: string;
    absPath: string;
    size: number;
    modifiedAt: string | null;
};

export type TextPreview = {
    content: string;
    startLine: number;
    endLine: number;
    truncated: boolean;
};

export type ChangeSummary = {
    dirName: string;
    changeName: string | null;
    currentStage: string | null;
    currentStageStatus: string | null;
    createdAt: string | null;
    updatedAt: string | null;
};

