from cogs.listings import RefreshResult


def test_empty_result_says_nothing_to_do():
    assert RefreshResult().summary() == "There are no active listings to refresh."


def test_clean_run_reports_only_the_count():
    assert RefreshResult(updated=4).summary() == "Re-rendered 4 listing post(s)."


def test_skipped_reasons_are_reported_separately():
    summary = RefreshResult(
        updated=2, missing_post=1, no_channel=3, unknown_poster=1
    ).summary()
    assert "Re-rendered 2" in summary
    assert "1 listing(s) have no post" in summary
    assert "3 listing(s) are for a sport whose channel I can't reach" in summary
    assert "1 listing(s) were left alone" in summary


def test_reasons_are_omitted_when_zero():
    summary = RefreshResult(updated=1, no_channel=2).summary()
    assert "no post in the channel" not in summary
    assert "couldn't look up" not in summary
    assert "channel I can't reach" in summary


def test_all_skipped_still_reports_the_zero_count():
    """A run that updated nothing but found listings must not look like success."""
    summary = RefreshResult(missing_post=2).summary()
    assert "Re-rendered 0 listing post(s)." in summary
    assert "2 listing(s) have no post" in summary
