from crete.framework.agent.services.cc import CCAgent
from crete.framework.context_builder.services.aixcc import AIxCCContextBuilder
from crete.framework.crete import Crete
from crete.framework.scheduler.services.round_robin import RoundRobinScheduler

app = Crete(
    id="app-cc",
    agents=[
        CCAgent(
            max_turns=100,
            max_budget_usd=10.0,
        ),
    ],
    scheduler=RoundRobinScheduler(early_exit=True, max_rounds=1),
)

if __name__ == "__main__":
    AIxCCContextBuilder.shell(app)
