from routine import build_review, infer_target


def test_target_mismatch_blocks_review_readiness():
    plan = build_review("Farm nearby NPCs for sword mastery using sword moves.", "Fruit", False)
    assert plan.prompt_target == "Sword"
    assert not plan.ready_for_review
    assert plan.conflicts


def test_movement_disabled_without_permission():
    plan = build_review("Attack nearby NPCs without moving.", "Fruit", False)
    assert not plan.movement_allowed
    assert "Remain stationary" in " ".join(plan.steps)


def test_explicit_movement_is_visible_in_plan():
    plan = build_review("Move toward nearby NPCs and attack.", "Fruit", False)
    assert plan.movement_allowed
    assert "explicitly mentions" in plan.movement_reason


def test_setting_can_authorize_movement():
    plan = build_review("Attack nearby NPCs.", "Fruit", True)
    assert plan.movement_allowed


def test_ambiguous_target_is_not_silently_chosen():
    plan = build_review("Use my fruit and sword to fight NPCs.", "Fruit", False)
    assert not plan.ready_for_review
    assert plan.conflicts


def test_live_execution_always_disabled_in_prototype():
    plan = build_review("Farm nearby NPCs for fruit mastery.", "Fruit", False)
    assert plan.ready_for_review
    assert plan.live_execution_enabled is False


def test_no_prompt_is_blocked():
    plan = build_review("", "Fruit", False)
    assert not plan.ready_for_review


def test_infer_target():
    assert infer_target("I need sword mastery") == "Sword"
    assert infer_target("train my fruit") == "Fruit"
    assert infer_target("use my gun") == "Gun"
    assert infer_target("train fighting style") == "Fighting style"
    assert infer_target("fight using fruit and sword") is None
