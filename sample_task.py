"""High-level task shared with all agents; never includes payoff realizations."""
from schemas import AGENT_IDS

TASK = f"""You are one of {len(AGENT_IDS)} equal-status AssistAI employees. Across eight weeks,
maximize cumulative customer-weeks (sum of customer counts at each week's end).
Each employee controls only their own {{HOURS_PER_WEEK}} weekly hours. Discuss strategy via
[CHAT] @all or [CHAT] @agent_b @agent_c messages first (direct messages may
target any subset of other agents; sending and receiving cost work time),
then allocate remaining hours across 16 features in four independent branches.
Each branch has an initial feature and three sequential add-ons. An add-on
becomes available only after its immediate prerequisite was completed in a
prior week. Team members can focus on one branch or explore multiple branches.
Unfinished work carries over, but some progress may become outdated at week end. 
Work beyond the required hours for a feature is wasted. Completed features generate
persistent new customers, whose payoffs are hidden until completion. Later
add-ons have higher expected customer gains, but their actual payoffs are
uncertain; more required hours do not guarantee higher gains. Outcomes within
one branch may be related, but a successful feature does not guarantee a
successful add-on. Prior-week work allocations and payoffs are public.
Leadership emerges only through voluntary communication and coordination.
"""
