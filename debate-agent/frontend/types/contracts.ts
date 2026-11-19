// Selected v1 HTTP response shapes. Python Pydantic remains the source of truth.
export interface ProjectInput {
  motion: string; side: string; format: string; duration_seconds: number;
  competition_context: string; user_requirements: string;
}
export interface Project extends ProjectInput { id: string }
export interface TopicContent {
  background: string; target_audience: string; definitions: Record<string, string>;
  discussion_scope: string; judging_criteria: string[];
  core_conflicts: string[]; strategy_options: string[];
  [key: string]: unknown;
}
export interface Topic { id: string; version: number; status: string; content: TopicContent }
export interface Reasoning {
  id: string; label: string; content: string; children: Reasoning[];
}
export interface Argument {
  id: string; title: string; core_claim: string; explanation: string;
  reasoning_nodes: Reasoning[]; impact: string;
  evidence_needs: { id: string; question: string; acceptable_source: string }[];
  attack_defense: { opposing_claim: string; response: string; weighing: string }[];
}
export interface DebateCase {
  id: string; thesis: string; arguments: Argument[]; weighing: string;
  overall_strategy: string; [key: string]: unknown;
}
export interface WorkingCopy { id: string; edit_version: number; case: DebateCase }
export interface Revision { id: string; revision_number: number }
export interface Job { id: string; status: string; current_step: string; error_code: string | null }
