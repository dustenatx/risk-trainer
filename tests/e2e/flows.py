"""Browser steps shared by the local e2e tests and the deployed smoke test."""

from playwright.sync_api import Page, expect

FINDINGS_PER_SCENARIO = 5


def answer_all_transfer(page: Page) -> None:
    """Choose transfer for every finding once the scenario form is ready.

    Transfer is valid in any scenario (no slots, no approver needed). Links are
    hx-boosted, so a click returns before the scenario page is swapped in and
    `locator.all()` doesn't wait: wait for app.js to mark the form ready first.
    """
    expect(page.locator('form[data-slots][data-ready="1"]')).to_be_visible()
    radios = page.locator('input[type="radio"][value="transfer"]')
    expect(radios).to_have_count(FINDINGS_PER_SCENARIO)
    for radio in radios.all():
        radio.check()
    for radio in radios.all():
        expect(radio).to_be_checked()
