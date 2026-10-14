from routine import build_review, infer_target


def test_target_mismatch_blocks_review_readiness():
    plan = build_review("Review a sword mastery demonstration.", "Fruit", False)
    assert plan.prompt_target == "Sword"
    assert not plan.ready_for_review
    assert plan.conflicts


def test_movement_excluded_without_permission():
    plan = build_review("Review the fruit demonstration without movement.", "Fruit", False)
    assert not plan.movement_allowed
    assert any("does not issue movement" in step for step in plan.steps)


def test_explicit_movement_is_visible_in_plan_but_never_executed():
    plan = build_review("Move toward the marker in the demonstration.", "Fruit", False)
    assert plan.movement_allowed
    assert "review" in plan.movement_reason
    assert plan.live_execution_enabled is False


def test_setting_can_include_movement_in_advisory_plan():
    plan = build_review("Review the fruit demonstration.", "Fruit", True)
    assert plan.movement_allowed
    assert plan.live_execution_enabled is False


def test_ambiguous_target_is_not_silently_chosen():
    plan = build_review("Review the fruit and sword demonstration.", "Fruit", False)
    assert not plan.ready_for_review
    assert plan.conflicts


def test_live_execution_always_disabled_in_prototype():
    plan = build_review("Review the fruit demonstration.", "Fruit", False)
    assert plan.ready_for_review
    assert plan.live_execution_enabled is False


def test_no_prompt_is_blocked():
    plan = build_review("", "Fruit", False)
    assert not plan.ready_for_review


def test_infer_target():
    assert infer_target("Review sword mastery") == "Sword"
    assert infer_target("review my fruit") == "Fruit"
    assert infer_target("review gun indicator") == "Gun"
    assert infer_target("review fighting style") == "Fighting style"
    assert infer_target("review fruit and sword") is None


def test_negative_movement_instruction_does_not_authorize_movement():
    plan = build_review("Do not move; keep the recording stationary.", "Fruit", False)
    assert not plan.movement_allowed


def test_reset_if_stuck_is_not_assumed():
    plan = build_review("Review the fruit demonstration and note if it gets stuck.", "Fruit", False)
    assert not plan.reset_if_stuck


def test_explicit_reset_if_stuck_is_reported_as_manual_request():
    plan = build_review("If the character gets stuck, reset the character manually.", "Fruit", False)
    assert plan.reset_if_stuck
    assert any("remains manual" in rule for rule in plan.safety_rules)
    assert plan.live_execution_enabled is False


def test_negated_reset_is_not_reported_as_requested():
    plan = build_review("Do not reset the character if it gets stuck.", "Fruit", False)
    assert not plan.reset_if_stuck


def test_stopping_if_stuck_does_not_authorize_movement():
    plan = build_review("Review the demonstration and stop moving if stuck.", "Fruit", False)
    assert not plan.movement_allowed
