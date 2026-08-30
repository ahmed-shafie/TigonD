export type ChatMessage = {role:"user"|"assistant";content:string;model?:string;tools?:{tool:string;summary:string}[]};
export type AssistantReply = {conversation_id:string;answer:string;mode:"read_only";model:string;tools_used:{tool:string;summary:string}[];suggestions:string[];detail?:string};

