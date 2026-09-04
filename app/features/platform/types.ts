export type WorkspaceSummary = {workspace:"operations"|"data_quality"|"governance"|"administration";cards:Record<string,number|string>;actions:string[]};
export type LineageNode = {node_id:string;kind:"source"|"dataset"|"pipeline"|"quality_gate"|"target";label:string};
export type LineageEdge = {source:string;target:string;operation:string};
export type LineageGraph = {nodes:LineageNode[];edges:LineageEdge[]};
export type ConnectorCapability = {key:string;name:string;category:string;modes:string[];status:"ready"|"requires_driver"|"requires_runtime";required_fields:string[];secret_fields:string[]};
export type RuntimeCapability = {key:string;supports:string[];execution_status:"ready"|"adapter_ready_requires_runtime";health_endpoint:string};
