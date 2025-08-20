from typing import Callable
from unittest.mock import patch

import pytest
from llama_index.core.text_splitter import SentenceSplitter

from kiln_ai.adapters.chunkers.base_chunker import ChunkingResult
from kiln_ai.adapters.chunkers.fixed_window_chunker import FixedWindowChunker
from kiln_ai.datamodel.chunk import ChunkerConfig, ChunkerType


@pytest.fixture
def mock_fixed_window_chunker_factory() -> Callable[[int, int], FixedWindowChunker]:
    def create_chunker(chunk_size: int, chunk_overlap: int) -> FixedWindowChunker:
        return FixedWindowChunker(
            ChunkerConfig(
                name="test-chunker",
                chunker_type=ChunkerType.FIXED_WINDOW,
                properties={"chunk_size": chunk_size, "chunk_overlap": chunk_overlap},
            )
        )

    return create_chunker


async def test_fixed_window_chunker_wrong_chunker_type(
    mock_fixed_window_chunker_factory,
):
    with pytest.raises(ValueError):
        FixedWindowChunker(
            ChunkerConfig(
                name="test-chunker",
                chunker_type="wrong-chunker-type",
                properties={"chunk_size": 100, "chunk_overlap": 10},
            )
        )


async def test_fixed_window_chunker_chunk_empty_text(
    mock_fixed_window_chunker_factory,
):
    # we should not even be calling the splitter if the text is empty
    chunker = mock_fixed_window_chunker_factory(100, 10)
    with patch.object(SentenceSplitter, "split_text") as mock_split_text:
        assert await chunker.chunk("") == ChunkingResult(chunks=[])
        mock_split_text.assert_not_called()


@pytest.mark.parametrize(
    "chunk_size,chunk_overlap,expected_chunks",
    [(12, 6, 43), (256, 12, 2), (1024, 64, 1), (2048, 128, 1)],
)
async def test_fixed_window_chunker_concrete_chunker(
    chunk_size, chunk_overlap, expected_chunks, mock_fixed_window_chunker_factory
):
    """
    This test is to ensure that the chunker can split text (with markdown syntax). The specific values are just an illustration rather than values we
    particularly care about.
    """
    chunker = mock_fixed_window_chunker_factory(chunk_size, chunk_overlap)
    text_to_chunk = """# How Ice Cubes Make Drinks Colder

## Introduction

When you drop an ice cube into a drink, it does more than just float and look refreshing. It changes the thermal state of the liquid in a precise and physically predictable way. While it may seem like a simple act, the science behind how ice cubes make drinks colder is a fascinating interplay of thermodynamics, phase change, and heat transfer.

## The Science of Cooling

### Heat Transfer Basics

At the core of the process is the concept of **heat exchange**. Heat naturally flows from warmer objects to colder ones until thermal equilibrium is reached. When an ice cube, which is at 0°C (32°F), is placed in a drink that is warmer than that, heat begins to flow from the liquid to the ice. This transfer of energy cools the drink while simultaneously warming the ice.

### Latent Heat of Fusion

However, it's not just about the ice warming up. The real magic happens because of **latent heat**—specifically, the heat of fusion. When ice melts, it doesn't instantly become the same temperature as the liquid around it. Instead, it absorbs a significant amount of energy just to change from a solid to a liquid, without its temperature rising. This phase change requires approximately 334 joules per gram of ice, all taken from the drink, which cools as a result."""

    output = await chunker.chunk(text_to_chunk)
    assert len(output.chunks) == expected_chunks, (
        f"Expected {expected_chunks} chunks, got {len(output.chunks)}. If this is the result of an intentional change to chunk boundaries, please update the expected number of chunks in the test. Note that changes to chunk boundaries can have a downstream impact on retrieval."
    )


@pytest.mark.parametrize(
    "chunk_size,chunk_overlap,expected_chunks",
    [(12, 6, 120), (256, 12, 4), (1024, 64, 1), (2048, 128, 1)],
)
async def test_fixed_window_chunker_concrete_chunker_zh(
    chunk_size, chunk_overlap, expected_chunks, mock_fixed_window_chunker_factory
):
    """
    This test is to ensure that the chunker can split Chinese text. The specific values are just an illustration rather than values we
    particularly care about.
    """
    chunker = mock_fixed_window_chunker_factory(chunk_size, chunk_overlap)
    text_to_chunk = """火山是地表下在岩浆库中的高温岩浆及其有关的气体、碎屑从行星的地壳中喷出而形成的，具有特殊形態的地质结构。

岩石圈由若干板块组成，它们漂浮在地幔的软流层之上，在板块的交界处岩石圈比较破碎，地下岩浆容易在此喷发形成火山。[1] 火山可以分为死火山、休眠火山和活火山。在一段时间内，没有出現喷发事件的活火山叫做睡火山（休眠火山）。另外还有一种泥火山，它在科学上严格来说不属于火山，但是许多社会大众也把它看作是火山的一种类型。

火山爆发可能会造成许多危害，常伴有地震，影响范围不仅在火山爆发附近。其中一个危险是火山灰可能对飞机构成威胁，特别是那些喷气发动机，其中灰尘颗粒可以在高温下熔化; 熔化的颗粒随后粘附到涡轮机叶片并改变它们的形状，从而中断涡轮发动机的操作。大型爆发可能会影响气温，火山灰和硫酸液滴遮挡太阳辐射并冷却地球的低层大气（或对流层）; 然而，它们也吸收地球辐射的热量，从而使高层大气（或平流层）变暖。 历史上，火山冬天造成了灾难性的饥荒。

虽然火山喷发会对人类造成危害，但同时它也带来一些好处。例如：可以促进宝石的形成；扩大陆地的面积（夏威夷群岛就是由火山喷发而形成的）；作为观光旅游考察景点，推动旅游业，如日本的富士山。[2] 专门研究火山活动的学科称为火山学[3]。
"""  # noqa: RUF001

    output = await chunker.chunk(text_to_chunk)
    assert len(output.chunks) == expected_chunks, (
        f"Expected {expected_chunks} chunks, got {len(output.chunks)}. If this is the result of an intentional change to chunk boundaries, please update the expected number of chunks in the test. Note that changes to chunk boundaries can have a downstream impact on retrieval."
    )


@pytest.mark.parametrize(
    "chunk_size,chunk_overlap,expected_chunks",
    [(12, 6, 39), (256, 12, 1), (1024, 64, 1), (2048, 128, 1)],
)
async def test_fixed_window_chunker_concrete_chunker_no_punctuation(
    chunk_size, chunk_overlap, expected_chunks, mock_fixed_window_chunker_factory
):
    """
    This test is to ensure that the chunker still does some splitting even if there is no punctuation. The specific values are just an illustration rather than values we
    particularly care about.
    """
    chunker = mock_fixed_window_chunker_factory(chunk_size, chunk_overlap)
    text_to_chunk = """how ice cubes make drinks colder introduction when you drop an ice cube into a drink it does more than just float and look refreshing it changes the thermal state of the liquid in a precise and physically predictable way while it may seem like a simple act the science behind how ice cubes make drinks colder is a fascinating interplay of thermodynamics phase change and heat transfer the science of cooling heat transfer basics at the core of the process is the concept of heat exchange heat naturally flows from warmer objects to colder ones until thermal equilibrium is reached when an ice cube which is at 0c 32f is placed in a drink that is warmer than that heat begins to flow from the liquid to the ice this transfer of energy cools the drink while simultaneously warming the ice latent heat of fusion however its not just about the ice warming up the real magic happens because of latent heat specifically the heat of fusion when ice melts it doesnt instantly become the same temperature as the liquid around it instead it absorbs a significant amount of energy just to change from a solid to a liquid without its temperature rising this phase change requires approximately 334 joules per gram of ice all taken from the drink which cools as a result"""

    output = await chunker.chunk(text_to_chunk)
    assert len(output.chunks) == expected_chunks, (
        f"Expected {expected_chunks} chunks, got {len(output.chunks)}. If this is the result of an intentional change to chunk boundaries, please update the expected number of chunks in the test. Note that changes to chunk boundaries can have a downstream impact on retrieval."
    )


@pytest.mark.parametrize(
    "chunk_size,chunk_overlap,expected_chunks",
    [(12, 6, 106), (256, 12, 3), (1024, 64, 1), (2048, 128, 1)],
)
async def test_fixed_window_chunker_concrete_chunker_no_punctuation_zh(
    chunk_size, chunk_overlap, expected_chunks, mock_fixed_window_chunker_factory
):
    """
    This test is to ensure that the chunker still does some splitting even if there is no punctuation. The specific values are just an illustration rather than values we
    particularly care about.
    """
    text_to_chunk = "火山是地表下在岩浆库中的高温岩浆及其有关的气体碎屑从行星的地壳中喷出而形成的具有特殊形態的地质结构岩石圈由若干板块组成它们漂浮在地幔的软流层之上在板块的交界处岩石圈比较破碎地下岩浆容易在此喷发形成火山火山可以分为死火山休眠火山和活火山在一段时间内没有出現喷发事件的活火山叫做睡火山休眠火山另外还有一种泥火山它在科学上严格来说不属于火山但是许多社会大众也把它看作是火山的一种类型火山爆发可能会造成许多危害常伴有地震影响范围不仅在火山爆发附近其中一个危险是火山灰可能对飞机构成威胁特别是那些喷气发动机其中灰尘颗粒可以在高温下熔化熔化的颗粒随后粘附到涡轮机叶片并改变它们的形状从而中断涡轮发动机的操作大型爆发可能会影响气温火山灰和硫酸液滴遮挡太阳辐射并冷却地球的低层大气或对流层然而它们也吸收地球辐射的热量从而使高层大气或平流层变暖历史上火山冬天造成了灾难性的饥荒虽然火山喷发会对人类造成危害但同时它也带来一些好处例如可以促进宝石的形成扩大陆地的面积夏威夷群岛就是由火山喷发而形成的作为观光旅游考察景点推动旅游业如日本的富士山专门研究火山活动的学科称为火山学"
    chunker = mock_fixed_window_chunker_factory(chunk_size, chunk_overlap)
    output = await chunker.chunk(text_to_chunk)
    assert len(output.chunks) == expected_chunks, (
        f"Expected {expected_chunks} chunks, got {len(output.chunks)}. If this is the result of an intentional change to chunk boundaries, please update the expected number of chunks in the test. Note that changes to chunk boundaries can have a downstream impact on retrieval."
    )


async def test_fixed_window_chunker_preserves_text_content(
    mock_fixed_window_chunker_factory,
):
    """
    Test that the chunker preserves the original text content when reassembled.
    """
    chunker = mock_fixed_window_chunker_factory(100, 10)
    text_to_chunk = (
        "This is a test sentence. This is another test sentence. And a third one."
    )

    output = await chunker.chunk(text_to_chunk)

    # Reassemble the text from chunks
    reassembled_text = " ".join(chunk.text for chunk in output.chunks)

    # The reassembled text should contain all the original content
    # (though spacing might differ due to chunking)
    assert "This is a test sentence" in reassembled_text
    assert "This is another test sentence" in reassembled_text
    assert "And a third one" in reassembled_text


@pytest.mark.parametrize(
    "text",
    ["   ", "\n\n\n", "\t\t\t", " \n\t "],
)
async def test_fixed_window_chunker_handles_whitespace_only(
    mock_fixed_window_chunker_factory,
    text,
):
    """
    Test that the chunker handles whitespace-only text appropriately.
    """
    chunker = mock_fixed_window_chunker_factory(100, 10)

    output = await chunker.chunk(text)

    # Should return empty chunks for whitespace-only text
    assert len(output.chunks) == 0


async def test_fixed_window_chunker_handles_special_characters(
    mock_fixed_window_chunker_factory,
):
    """
    Test that the chunker handles special characters and unicode properly.
    """
    chunker = mock_fixed_window_chunker_factory(50, 5)
    text_with_special_chars = (
        "Hello 🌍! This has emojis 🚀 and symbols ©®™. Also unicode: αβγδε."
    )

    output = await chunker.chunk(text_with_special_chars)

    # Should create at least one chunk
    assert len(output.chunks) > 0

    # Reassemble and check that special characters are preserved
    reassembled = " ".join(chunk.text for chunk in output.chunks)
    assert "Hello" in reassembled
    assert "This has emojis" in reassembled
    assert "🌍" in reassembled
    assert "🚀" in reassembled
    assert "©®™" in reassembled
    assert "αβγδε" in reassembled


async def test_fixed_window_chunker_handles_single_character(
    mock_fixed_window_chunker_factory,
):
    """
    Test that the chunker handles single character text.
    """
    chunker = mock_fixed_window_chunker_factory(100, 10)

    output = await chunker.chunk("A")
    assert len(output.chunks) == 1
    assert output.chunks[0].text == "A"


async def test_fixed_window_chunker_handles_single_word(
    mock_fixed_window_chunker_factory,
):
    """
    Test that the chunker handles single word text.
    """
    chunker = mock_fixed_window_chunker_factory(100, 10)

    output = await chunker.chunk("Hello")
    assert len(output.chunks) == 1
    assert output.chunks[0].text == "Hello"


async def test_fixed_window_chunker_handles_single_sentence(
    mock_fixed_window_chunker_factory,
):
    """
    Test that the chunker handles single sentence text.
    """
    chunker = mock_fixed_window_chunker_factory(100, 10)

    output = await chunker.chunk("This is a single sentence.")
    assert len(output.chunks) == 1
    assert output.chunks[0].text == "This is a single sentence."


async def test_fixed_window_chunker_very_large_text(mock_fixed_window_chunker_factory):
    """
    Test that the chunker can handle very large text without issues.
    """
    chunker = mock_fixed_window_chunker_factory(100, 10)

    # Create a large text by repeating a sentence
    large_text = "This is a test sentence. " * 1000

    output = await chunker.chunk(large_text)

    # Should produce multiple chunks
    assert len(output.chunks) > 1

    # All chunks should have content
    for chunk in output.chunks:
        assert chunk.text.strip() != ""
