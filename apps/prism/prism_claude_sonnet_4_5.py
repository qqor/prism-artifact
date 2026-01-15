from crete.framework.agent.services.prism import PrismAgent
from crete.framework.context_builder.services.aixcc import AIxCCContextBuilder
from crete.framework.crete import Crete
from crete.framework.scheduler.services.round_robin import RoundRobinScheduler
from python_llm.api.actors import LlmApiManager

app = Crete(
    id="app-prism-claude-sonnet-4-5-20250929",
    agents=[
        PrismAgent(
            llm_api_manager=LlmApiManager.from_environment(
                model="claude-sonnet-4-5-20250929", custom_llm_provider="anthropic"
            ),
            backup_llm_api_manager=LlmApiManager.from_environment(
                model="claude-sonnet-4-5-20250929"
            ),
            max_n_evals=6,
            recursion_limit=256,
        ),
    ],
    scheduler=RoundRobinScheduler(early_exit=True, max_rounds=1),
)

if __name__ == "__main__":
    AIxCCContextBuilder.shell(app)
