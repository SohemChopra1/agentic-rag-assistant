from app.retrieval.chunker import MAX_CHUNK_WORDS, TARGET_CHUNK_WORDS, chunk_text


def test_short_text_is_one_chunk():
    text = "Progressive overload is the gradual increase of stress placed on the body during exercise."
    chunks = chunk_text(text)
    assert len(chunks) == 1
    assert chunks[0].section is None
    assert "Progressive overload" in chunks[0].content


def test_heading_sets_section_for_following_chunks():
    text = (
        "# Protein Recommendations\n\n"
        "Adults engaged in regular resistance training generally need more "
        "protein than sedentary adults to support muscle repair and growth."
    )
    chunks = chunk_text(text)
    assert len(chunks) == 1
    assert chunks[0].section == "Protein Recommendations"
    assert "resistance training" in chunks[0].content


def test_heading_glued_to_text_without_blank_line_still_splits():
    text = "## Hydration\nDrink water regularly throughout the day, especially around exercise."
    chunks = chunk_text(text)
    assert chunks[0].section == "Hydration"
    assert "Drink water" in chunks[0].content


def test_multiple_sections_tracked_independently():
    text = (
        "# Cardio\n\nRunning improves cardiovascular endurance over time.\n\n"
        "# Strength\n\nResistance training builds muscular strength and bone density."
    )
    chunks = chunk_text(text)
    sections = [c.section for c in chunks]
    assert "Cardio" in sections
    assert "Strength" in sections
    cardio_chunk = next(c for c in chunks if c.section == "Cardio")
    strength_chunk = next(c for c in chunks if c.section == "Strength")
    assert "Running" in cardio_chunk.content
    assert "Resistance training" in strength_chunk.content


def test_long_document_splits_into_multiple_chunks_with_overlap():
    # Build several distinct paragraphs that together exceed TARGET_CHUNK_WORDS
    paragraphs = [f"Paragraph {i} discusses topic {i} in some reasonable amount of detail here today now." for i in range(20)]
    text = "\n\n".join(paragraphs)

    chunks = chunk_text(text)
    assert len(chunks) > 1
    # every chunk should respect the target size reasonably closely (allowing for the seeded overlap)
    for c in chunks[:-1]:
        assert c.word_count <= TARGET_CHUNK_WORDS + 20


def test_oversized_single_paragraph_gets_sentence_split():
    sentence = "Consistent training volume matters for long term progress. "
    huge_paragraph = sentence * 60  # way over MAX_CHUNK_WORDS as one paragraph
    chunks = chunk_text(huge_paragraph)

    assert len(chunks) > 1
    assert all(c.word_count <= MAX_CHUNK_WORDS for c in chunks)


def test_empty_text_returns_no_chunks():
    assert chunk_text("") == []
    assert chunk_text("   \n\n  ") == []
