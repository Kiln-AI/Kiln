from kiln_ai.datamodel.prompt import (
    BasePrompt,
    ChainOfThoughtThinkingStrategy,
    ReActThinkingStrategy,
    ThinkingStrategyType,
)


def test_chain_of_thought_strategy():
    """Test ChainOfThoughtThinkingStrategy creation and properties."""
    strategy = ChainOfThoughtThinkingStrategy()
    assert strategy.type == ThinkingStrategyType.chain_of_thought
    assert strategy.instructions == "Think step by step, explaining your reasoning."

    # Test custom values
    custom_strategy = ChainOfThoughtThinkingStrategy(
        instructions="Custom thinking instructions"
    )
    assert custom_strategy.instructions == "Custom thinking instructions"


def test_react_strategy():
    """Test ReActThinkingStrategy creation and properties."""
    strategy = ReActThinkingStrategy()
    assert strategy.type == ThinkingStrategyType.react
    assert "Think step by step" in strategy.instructions

    # Test custom values
    custom_strategy = ReActThinkingStrategy(
        instructions="Custom ReAct instructions",
    )
    assert custom_strategy.instructions == "Custom ReAct instructions"


def test_strategy_validation():
    """Test validation constraints on strategy parameters."""
    # Test that strategies can be created with valid instructions
    strategy1 = ChainOfThoughtThinkingStrategy(instructions="Valid instructions")
    assert strategy1.instructions == "Valid instructions"

    strategy2 = ReActThinkingStrategy(instructions="Valid ReAct instructions")
    assert strategy2.instructions == "Valid ReAct instructions"


def test_base_prompt_with_thinking_strategies():
    """Test BasePrompt with different thinking strategies."""
    # Test with NoThinkingStrategy (default)
    prompt = BasePrompt(name="test", prompt="test prompt")
    assert prompt.thinkingStrategy is None
    assert prompt.get_thinking_instructions() is None
    assert not prompt.has_thinking_strategy()

    # Test with ChainOfThoughtThinkingStrategy
    cot_strategy = ChainOfThoughtThinkingStrategy(instructions="Think carefully")
    prompt = BasePrompt(
        name="test", prompt="test prompt", thinkingStrategy=cot_strategy
    )
    assert isinstance(prompt.thinkingStrategy, ChainOfThoughtThinkingStrategy)
    assert prompt.get_thinking_instructions() == "Think carefully"
    assert prompt.has_thinking_strategy()

    # Test with ReActThinkingStrategy
    react_strategy = ReActThinkingStrategy(instructions="Reason and act")
    prompt = BasePrompt(
        name="test", prompt="test prompt", thinkingStrategy=react_strategy
    )
    assert isinstance(prompt.thinkingStrategy, ReActThinkingStrategy)
    assert prompt.get_thinking_instructions() == "Reason and act"
    assert prompt.has_thinking_strategy()


def test_backward_compatibility_upgrade():
    """Test that old chain_of_thought_instructions are properly upgraded."""
    # Test with chain_of_thought_instructions provided
    data = {
        "name": "test",
        "prompt": "test prompt",
        "chain_of_thought_instructions": "Think step by step",
    }
    prompt = BasePrompt.model_validate(data)
    assert isinstance(prompt.thinkingStrategy, ChainOfThoughtThinkingStrategy)
    assert prompt.thinkingStrategy.instructions == "Think step by step"
    assert prompt.get_thinking_instructions() == "Think step by step"

    # Test with chain_of_thought_instructions as None
    data = {
        "name": "test",
        "prompt": "test prompt",
        "chain_of_thought_instructions": None,
    }
    prompt = BasePrompt.model_validate(data)
    assert prompt.thinkingStrategy is None
    assert prompt.get_thinking_instructions() is None

    # Test with no chain_of_thought_instructions (should use default)
    data = {"name": "test", "prompt": "test prompt"}
    prompt = BasePrompt.model_validate(data)
    assert prompt.thinkingStrategy is None


def test_thinking_strategy_serialization():
    """Test that thinking strategies serialize and deserialize correctly."""
    # Test ChainOfThoughtThinkingStrategy
    original = ChainOfThoughtThinkingStrategy(instructions="Test instructions")
    serialized = original.model_dump()
    deserialized = ChainOfThoughtThinkingStrategy.model_validate(serialized)
    assert deserialized.instructions == "Test instructions"

    # Test ReActThinkingStrategy
    original = ReActThinkingStrategy(instructions="Test ReAct")
    serialized = original.model_dump()
    deserialized = ReActThinkingStrategy.model_validate(serialized)
    assert deserialized.instructions == "Test ReAct"


def test_prompt_with_mixed_strategies():
    """Test that prompts can be created with different strategy types."""
    strategies = [
        ChainOfThoughtThinkingStrategy(instructions="Custom COT"),
        ReActThinkingStrategy(instructions="Custom ReAct"),
    ]

    for i, strategy in enumerate(strategies):
        prompt = BasePrompt(
            name=f"test_{i}", prompt="test prompt", thinkingStrategy=strategy
        )
        assert prompt.thinkingStrategy is not None
        assert prompt.thinkingStrategy.type == strategy.type
        assert prompt.has_thinking_strategy()
