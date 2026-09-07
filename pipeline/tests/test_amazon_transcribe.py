from mac_transcribe.amazon_transcribe import parse_transcribe_result


def _item(type_, content, start=None, end=None):
    item = {"type": type_, "alternatives": [{"content": content}]}
    if start is not None:
        item["start_time"] = start
    if end is not None:
        item["end_time"] = end
    return item


def test_parse_transcribe_result_groups_words_by_speaker_turn():
    data = {
        "results": {
            "items": [
                _item("pronunciation", "Hello", start="0.0", end="0.5"),
                _item("pronunciation", "there", start="0.5", end="1.0"),
                _item("punctuation", "."),
                _item("pronunciation", "Hi", start="2.0", end="2.5"),
                _item("pronunciation", "back", start="2.5", end="3.0"),
                _item("punctuation", "."),
            ],
            "speaker_labels": {
                "segments": [
                    {"speaker_label": "spk_0", "items": [{"start_time": "0.0"}, {"start_time": "0.5"}]},
                    {"speaker_label": "spk_1", "items": [{"start_time": "2.0"}, {"start_time": "2.5"}]},
                ]
            },
        }
    }

    segments = parse_transcribe_result(data)

    assert segments == [
        {"start": 0.0, "end": 1.0, "text": "Hello there.", "speaker": 1},
        {"start": 2.0, "end": 3.0, "text": "Hi back.", "speaker": 2},
    ]


def test_parse_transcribe_result_renumbers_speakers_in_first_appearance_order():
    """Transcribe's raw spk_0/spk_1 labels are meaningless to a human reader
    -- and don't necessarily appear in numeric order in the transcript, so
    the renumbering must follow appearance order, not label sort order."""
    data = {
        "results": {
            "items": [
                _item("pronunciation", "First", start="0.0", end="0.5"),
                _item("pronunciation", "second", start="1.0", end="1.5"),
            ],
            "speaker_labels": {
                "segments": [
                    {"speaker_label": "spk_3", "items": [{"start_time": "0.0"}]},
                    {"speaker_label": "spk_1", "items": [{"start_time": "1.0"}]},
                ]
            },
        }
    }

    segments = parse_transcribe_result(data)

    assert [s["speaker"] for s in segments] == [1, 2]


def test_parse_transcribe_result_without_speaker_labels():
    data = {
        "results": {
            "items": [_item("pronunciation", "Solo", start="0.0", end="0.5")],
        }
    }

    segments = parse_transcribe_result(data)

    assert segments == [{"start": 0.0, "end": 0.5, "text": "Solo", "speaker": None}]
