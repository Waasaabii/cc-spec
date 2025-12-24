// types/projects.ts - Project registry types

export type ProjectRecord = {
    id: string;
    name: string;
    path: string;
    created_at: string;
    updated_at: string;
    last_opened_at?: string | null;
};
