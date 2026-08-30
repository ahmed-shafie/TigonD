from .assistant import AssistantEngine
from .application.use_cases.skills import BrowseSkills
from .application.use_cases.assistant import AskAssistant
from .application.use_cases.operational_actions import OperationalActionService
from .application.use_cases.intelligence_loop import IntelligenceLoop
from .application.use_cases.platform_catalog import PlatformCatalog
from .config import get_settings
from .infrastructure.skills import BuiltinSkillRegistry
from .intelligence import IntelligenceEngine
from .nifi import NiFiClient, NiFiFlowCompiler
from .postgres import PostgresService
from .proposals import PipelineProposalEngine
from .repository import SourceRepository
from .vault import VaultSecretStore


settings = get_settings()
secret_store = VaultSecretStore(settings.vault_url, settings.vault_token, settings.vault_mount)
repository = SourceRepository(settings.metadata_database_url, secret_store)
postgres = PostgresService(settings.query_timeout_seconds, settings.profile_sample_rows)
intelligence = IntelligenceEngine()
nifi_compiler = NiFiFlowCompiler()
nifi_client = NiFiClient(settings.nifi_url, settings.nifi_username, settings.nifi_password, settings.nifi_verify_ssl)
assistant = AssistantEngine(settings.ollama_url, settings.ollama_model, settings.ollama_enabled)
proposal_engine = PipelineProposalEngine()
skill_browser = BrowseSkills(BuiltinSkillRegistry())
operational_actions = OperationalActionService()
intelligence_loop = IntelligenceLoop()
platform_catalog = PlatformCatalog()


def get_repository() -> SourceRepository:
    return repository


def get_postgres() -> PostgresService:
    return postgres


def get_nifi() -> NiFiClient:
    return nifi_client


def get_assistant() -> AssistantEngine:
    return assistant


def get_skill_browser() -> BrowseSkills:
    return skill_browser


def get_ask_assistant() -> AskAssistant:
    return AskAssistant(repository, assistant)


def get_operational_actions() -> OperationalActionService:
    return operational_actions


def get_intelligence_loop() -> IntelligenceLoop:
    return intelligence_loop


def get_platform_catalog() -> PlatformCatalog:
    return platform_catalog
