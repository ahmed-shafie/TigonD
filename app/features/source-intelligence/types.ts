export type SourceForm = {name:string;host:string;port:string;database:string;username:string;password:string;sslmode:string};
export type DataObject = {schema_name:string;object_name:string;object_type:"table"|"view";estimated_rows:number|null};
export type RuntimeScore = {runtime:string;score:number;evidence:string[];risks:string[]};
export type SourceAssessment = {assessment_id:string;recommended_runtime:string;confidence:number;quality_score:number;pii_columns:string[];business_key_candidates:string[];watermark_candidates:string[];summary:string;runtime_scores:RuntimeScore[];pipeline_draft:{load_strategy:string;business_key:string|null;watermark_column:string|null;quality_gates:string[];status:string}};
export type FlowDeployment = {deployment_id:string;version:number;external_flow_id:string|null;status:"generated"|"deployed"|"running"|"stopped"|"failed"};

