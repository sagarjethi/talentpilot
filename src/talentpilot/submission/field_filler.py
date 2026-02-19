"""Fill visible form fields (phone, text, dropdown, radio) from responses.yaml."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from talentpilot.browser.base import BrowserAdapter

logger = logging.getLogger(__name__)

# CSS selectors tried in order when looking for a phone/mobile input
_PHONE_CSS_CANDIDATES = [
    "input[type='tel']",
    "input[name*='phone' i]",
    "input[id*='phone' i]",
    "input[aria-label*='phone' i]",
    "input[placeholder*='phone' i]",
    "input[name*='mobile' i]",
    "input[id*='mobile' i]",
    "input[aria-label*='mobile' i]",
    "input[placeholder*='mobile' i]",
    "input[name*='cell' i]",
    "input[aria-label*='cell' i]",
    "input[data-test-single-line-text-input]",
]


async def _fill_phone_if_present(adapter: BrowserAdapter, phone: str) -> bool:
    """Attempt to locate and fill an empty phone number field.

    Returns ``True`` if a field was filled.
    """
    if not phone:
        return False

    # Try CSS-based selectors first
    for css in _PHONE_CSS_CANDIDATES:
        elements = await adapter.query_all(css)
        for el in elements:
            try:
                visible = await el.is_visible()
                if not visible:
                    continue
                current = await el.get_attribute("value") or ""
                if current.strip():
                    continue
                await el.fill(phone)
                logger.debug("Filled phone number via selector: %s", css)
                return True
            except Exception:
                continue

    # JS fallback: find inputs whose label contains phone/mobile/cell
    try:
        filled = await adapter.evaluate("""
            (phone) => {
                const labels = document.querySelectorAll('label');
                for (const lbl of labels) {
                    const text = lbl.innerText.trim().toLowerCase();
                    if (text.includes('phone') || text.includes('mobile') || text.includes('cell')) {
                        const forAttr = lbl.getAttribute('for');
                        let input = forAttr ? document.getElementById(forAttr) : null;
                        if (!input) input = lbl.querySelector('input');
                        if (!input) input = lbl.parentElement?.querySelector('input');
                        if (input && input.offsetParent !== null && !input.value.trim()) {
                            input.focus();
                            input.value = phone;
                            input.dispatchEvent(new Event('input', {bubbles: true}));
                            input.dispatchEvent(new Event('change', {bubbles: true}));
                            return true;
                        }
                    }
                }
                return false;
            }
        """, phone)
        if filled:
            logger.debug("Filled phone number via JS label search.")
            return True
    except Exception:
        pass

    return False


async def _fill_text_inputs(
    adapter: BrowserAdapter, responses: dict[str, str]
) -> None:
    """Match visible text inputs to *responses* keys by label text."""
    labels = await adapter.query_all("label")
    for label_el in labels:
        label_text = (await label_el.inner_text()).strip().lower()
        if not label_text:
            continue

        # Find matching response (substring match, case-insensitive)
        match_value: str | None = None
        for key, val in responses.items():
            if key in label_text:
                match_value = str(val)
                break
        if match_value is None:
            continue

        # Locate the associated input
        for_attr = await label_el.get_attribute("for")
        if not for_attr:
            continue
        inp = await adapter.query(f"#{for_attr}", timeout=2_000)
        if inp is None:
            continue
        visible = await inp.is_visible()
        if not visible:
            continue

        tag = await inp.evaluate("el => el.tagName.toLowerCase()")
        if tag == "input":
            current = await inp.get_attribute("value") or ""
            if not current.strip():
                await inp.fill(match_value)
                logger.debug("Filled input '%s' with '%s'.", label_text, match_value)
        elif tag == "textarea":
            current = await inp.evaluate("el => el.value") or ""
            if not current.strip():
                await inp.fill(match_value)
                logger.debug("Filled textarea '%s'.", label_text)


async def _fill_dropdowns(
    adapter: BrowserAdapter, responses: dict[str, str], experience_years: int = 3
) -> None:
    """Match visible <select> elements and choose the closest option.

    Uses JS-based approach primarily to avoid stale element errors.
    """
    try:
        await adapter.evaluate("""
            (args) => {
                const responses = args.responses;
                const applicantYears = args.experienceYears;
                const selects = document.querySelectorAll('select');
                for (const sel of selects) {
                    if (sel.offsetParent === null) continue; // hidden

                    // Get label text — try multiple strategies
                    let labelText = '';
                    if (sel.id) {
                        const lbl = document.querySelector('label[for="' + sel.id + '"]');
                        if (lbl) labelText = lbl.innerText.trim().toLowerCase();
                    }
                    if (!labelText) labelText = (sel.getAttribute('aria-label') || '').trim().toLowerCase();
                    if (!labelText) {
                        // Try parent/sibling label or span
                        const parent = sel.closest('.fb-dash-form-element') ||
                                       sel.closest('[class*="form"]') ||
                                       sel.parentElement;
                        if (parent) {
                            const lbl = parent.querySelector('label, legend, span[class*="label"]');
                            if (lbl) labelText = lbl.innerText.trim().toLowerCase();
                        }
                    }
                    if (!labelText) {
                        // Check name attribute for clues
                        const name = (sel.name || sel.id || '').toLowerCase();
                        if (name.includes('country')) labelText = 'country';
                        else if (name.includes('phone')) labelText = 'phone country code';
                    }
                    if (!labelText) continue;

                    // Skip if already has a real value
                    const currentText = sel.options[sel.selectedIndex]?.text?.trim().toLowerCase() || '';
                    if (currentText && currentText !== 'select an option' && currentText !== 'select' && currentText !== '--') continue;

                    // Special handling: Country / Country Code dropdowns
                    const isCountrySelect = labelText.includes('country') ||
                                            labelText.includes('nation') ||
                                            labelText.includes('phone country');
                    if (isCountrySelect) {
                        // Look for the configured country in responses
                        let targetCountry = null;
                        for (const [key, val] of Object.entries(responses)) {
                            if (key.toLowerCase().includes('country')) {
                                targetCountry = String(val);
                                break;
                            }
                        }
                        if (!targetCountry) targetCountry = 'India';

                        const options = Array.from(sel.options);
                        for (const opt of options) {
                            const optText = opt.text.trim();
                            if (optText.toLowerCase().includes(targetCountry.toLowerCase()) ||
                                targetCountry.toLowerCase().includes(optText.toLowerCase())) {
                                sel.value = opt.value;
                                sel.dispatchEvent(new Event('change', {bubbles: true}));
                                break;
                            }
                        }
                        continue;
                    }

                    // Find matching response
                    let matchValue = null;
                    for (const [key, val] of Object.entries(responses)) {
                        if (labelText.includes(key.toLowerCase())) {
                            matchValue = String(val);
                            break;
                        }
                    }

                    // Smart experience detection: "Do you have more than X years..."
                    // Uses applicant_experience_years from settings.yaml
                    if (!matchValue) {
                        const expMatch = labelText.match(/(\d+)\s*(?:\+\s*)?years?\s*(?:of\s*)?(?:relevant\s*)?(?:work\s*)?experience/i);
                        if (expMatch) {
                            const requiredYears = parseInt(expMatch[1], 10);
                            matchValue = requiredYears <= applicantYears ? 'Yes' : 'No';
                        }
                    }

                    const options = Array.from(sel.options);
                    if (matchValue) {
                        for (const opt of options) {
                            const optText = opt.text.trim();
                            if (optText.toLowerCase() === matchValue.toLowerCase() ||
                                optText.toLowerCase().includes(matchValue.toLowerCase()) ||
                                matchValue.toLowerCase().includes(optText.toLowerCase())) {
                                sel.value = opt.value;
                                sel.dispatchEvent(new Event('change', {bubbles: true}));
                                break;
                            }
                        }
                    } else {
                        // Fallback: select "Yes" if available, else first real option
                        const yesOpt = options.find(o => o.text.trim().toLowerCase() === 'yes');
                        if (yesOpt) {
                            sel.value = yesOpt.value;
                            sel.dispatchEvent(new Event('change', {bubbles: true}));
                        } else {
                            const firstReal = options.find(o => {
                                const t = o.text.trim().toLowerCase();
                                return t && t !== 'select an option' && t !== 'select' && t !== '--' && t !== '';
                            });
                            if (firstReal) {
                                sel.value = firstReal.value;
                                sel.dispatchEvent(new Event('change', {bubbles: true}));
                            }
                        }
                    }
                }
            }
        """, {"responses": dict(responses), "experienceYears": experience_years})
        logger.debug("Dropdowns filled via JS.")
    except Exception as exc:
        logger.debug("JS dropdown fill failed: %s", exc)


async def _fill_radio_buttons(
    adapter: BrowserAdapter, responses: dict[str, str], experience_years: int = 3
) -> None:
    """Match radio-button groups by their fieldset legend or label text.

    Handles both standard ``<input type="radio">`` elements and LinkedIn's
    custom ``data-test-text-selectable-option__label`` labels.
    """
    # --- JS-based approach (handles LinkedIn SDUI) ---
    try:
        await adapter.evaluate("""
            (args) => {
                const responses = args.responses;
                const applicantYears = args.experienceYears;
                const fieldsets = document.querySelectorAll('fieldset');
                for (const fs of fieldsets) {
                    const legend = fs.querySelector('legend, span');
                    if (!legend) continue;
                    const groupLabel = legend.innerText.trim().toLowerCase();
                    if (!groupLabel) continue;

                    let matchValue = null;
                    for (const [key, val] of Object.entries(responses)) {
                        if (groupLabel.includes(key.toLowerCase())) {
                            matchValue = String(val).trim().toLowerCase();
                            break;
                        }
                    }

                    // Smart experience detection for radio buttons
                    // Uses applicant_experience_years from settings.yaml
                    if (!matchValue) {
                        const expMatch = groupLabel.match(/(\d+)\s*(?:\+\s*)?years?\s*(?:of\s*)?(?:relevant\s*)?(?:work\s*)?experience/i);
                        if (expMatch) {
                            const requiredYears = parseInt(expMatch[1], 10);
                            matchValue = requiredYears <= applicantYears ? 'yes' : 'no';
                        }
                    }

                    if (!matchValue) continue;

                    // Try LinkedIn's custom selectable labels first
                    const optLabels = fs.querySelectorAll('label[data-test-text-selectable-option__label]');
                    for (const lbl of optLabels) {
                        const text = (lbl.getAttribute('data-test-text-selectable-option__label') || '').toLowerCase();
                        if (matchValue.includes(text) || text.includes(matchValue)) {
                            // Click the associated radio input
                            const forId = lbl.getAttribute('for');
                            const radio = forId ? document.getElementById(forId) : null;
                            if (radio) {
                                radio.click();
                            } else {
                                lbl.click();
                            }
                            break;
                        }
                    }

                    // Fallback: standard radio inputs
                    if (optLabels.length === 0) {
                        const radios = fs.querySelectorAll('input[type="radio"]');
                        for (const r of radios) {
                            const closestLabel = r.closest('label') ||
                                r.parentElement?.querySelector('label');
                            let rText = closestLabel ? closestLabel.innerText.trim().toLowerCase() : '';
                            if (!rText) rText = (r.value || '').toLowerCase();
                            if (matchValue.includes(rText) || rText.includes(matchValue)) {
                                r.click();
                                break;
                            }
                        }
                    }
                }
            }
        """, {"responses": dict(responses), "experienceYears": experience_years})
        logger.debug("Radio buttons filled via JS.")
    except Exception as exc:
        logger.debug("JS radio fill failed: %s — trying Playwright fallback.", exc)

    # --- Playwright fallback for any missed radios ---
    fieldsets = await adapter.query_all("fieldset")
    for fs in fieldsets:
        legend = await fs.query_selector("legend")
        group_label = ""
        if legend:
            try:
                group_label = (await legend.inner_text()).strip().lower()
            except Exception:
                pass
        if not group_label:
            span = await fs.query_selector("span")
            if span:
                try:
                    group_label = (await span.inner_text()).strip().lower()
                except Exception:
                    pass
        if not group_label:
            continue

        match_value: str | None = None
        for key, val in responses.items():
            if key in group_label:
                match_value = str(val).strip().lower()
                break
        if match_value is None:
            continue

        # Check if already selected
        checked = await fs.query_selector("input[type='radio']:checked")
        if checked:
            continue

        radios = await fs.query_selector_all("input[type='radio']")
        for radio in radios:
            radio_label_el = await radio.evaluate_handle(
                "el => el.closest('label') || el.parentElement.querySelector('label')"
            )
            radio_text = ""
            if radio_label_el:
                try:
                    radio_text = (await radio_label_el.inner_text()).strip().lower()
                except Exception:
                    pass

            if not radio_text:
                radio_val = await radio.get_attribute("value") or ""
                radio_text = radio_val.strip().lower()

            if match_value in radio_text or radio_text in match_value:
                try:
                    await radio.evaluate("el => el.click()")
                except Exception:
                    try:
                        await radio.click(force=True, timeout=3_000)
                    except Exception:
                        pass
                logger.debug("Selected radio '%s' → '%s'.", group_label, radio_text)
                break


async def _scroll_form_into_view(adapter: BrowserAdapter) -> None:
    """Scroll the Easy Apply modal/form to reveal all fields.

    LinkedIn wraps the form in a scrollable container.  We scroll it
    incrementally so that Playwright can interact with fields that
    were below the fold.
    """
    try:
        await adapter.evaluate("""
            () => {
                // LinkedIn modal scrollable container candidates
                const containers = [
                    document.querySelector('.jobs-easy-apply-content'),
                    document.querySelector('[class*="easy-apply"] [class*="content"]'),
                    document.querySelector('.artdeco-modal__content'),
                    document.querySelector('[role="dialog"] [class*="body"]'),
                    document.querySelector('[role="dialog"]'),
                ];
                for (const c of containers) {
                    if (c && c.scrollHeight > c.clientHeight) {
                        c.scrollTop = c.scrollHeight;
                        return;
                    }
                }
                // Fallback: scroll the whole page
                window.scrollTo(0, document.body.scrollHeight);
            }
        """)
    except Exception:
        pass


async def _fill_fields_via_js(
    adapter: BrowserAdapter,
    input_responses: dict[str, str],
    phone: str,
) -> None:
    """JS-based fallback that finds inputs by their label text and fills them.

    This works even when Playwright can't see the elements (hidden behind
    LinkedIn's SDUI / hashed class names), by matching label text against
    the responses dictionary.
    """
    try:
        await adapter.evaluate("""
            (args) => {
                const responses = args.responses;
                const phone = args.phone;

                // Helper: set value with React/LinkedIn-compatible events
                function setValue(input, value) {
                    const nativeInputValueSetter = Object.getOwnPropertyDescriptor(
                        window.HTMLInputElement.prototype, 'value'
                    )?.set;
                    if (nativeInputValueSetter) {
                        nativeInputValueSetter.call(input, value);
                    } else {
                        input.value = value;
                    }
                    input.dispatchEvent(new Event('input', {bubbles: true}));
                    input.dispatchEvent(new Event('change', {bubbles: true}));
                    input.dispatchEvent(new Event('blur', {bubbles: true}));
                }

                // Find all labels and their associated inputs
                const labels = document.querySelectorAll('label');
                for (const lbl of labels) {
                    const labelText = lbl.innerText.trim().toLowerCase();
                    if (!labelText) continue;

                    // Find associated input
                    const forAttr = lbl.getAttribute('for');
                    let input = forAttr ? document.getElementById(forAttr) : null;
                    if (!input) input = lbl.querySelector('input, textarea, select');
                    if (!input) {
                        const parent = lbl.closest('.fb-dash-form-element') ||
                                       lbl.closest('[class*="form"]') ||
                                       lbl.parentElement;
                        if (parent) input = parent.querySelector('input, textarea, select');
                    }
                    if (!input) continue;
                    if (input.value && input.value.trim()) continue;  // Already filled

                    // Check for phone field
                    if ((labelText.includes('phone') || labelText.includes('mobile') ||
                         labelText.includes('cell')) && input.type !== 'select-one') {
                        if (phone && !input.value.trim()) {
                            setValue(input, phone);
                            continue;
                        }
                    }

                    // Match against responses
                    for (const [key, val] of Object.entries(responses)) {
                        if (labelText.includes(key.toLowerCase())) {
                            if (input.tagName === 'SELECT') {
                                const options = input.querySelectorAll('option');
                                for (const opt of options) {
                                    if (opt.text.toLowerCase().includes(String(val).toLowerCase())) {
                                        input.value = opt.value;
                                        input.dispatchEvent(new Event('change', {bubbles: true}));
                                        break;
                                    }
                                }
                            } else {
                                setValue(input, String(val));
                            }
                            break;
                        }
                    }
                }
            }
        """, {"responses": input_responses, "phone": phone})
    except Exception as exc:
        logger.debug("JS field fill fallback failed: %s", exc)


async def populate_visible_fields(
    adapter: BrowserAdapter,
    phone: str,
    responses: dict[str, dict[str, str]],
    experience_years: int = 3,
) -> None:
    """Fill every recognised field on the current form page.

    *responses* should have keys ``input_field``, ``radio``, ``dropdown``.
    *experience_years* is used for smart answers to "Do you have X years..." questions.

    Strategy:
    1. Scroll the form container to reveal all fields.
    2. Fill fields using Playwright-native selectors.
    3. Use a JS fallback to catch anything Playwright missed.
    """
    # Scroll to reveal all fields
    await _scroll_form_into_view(adapter)
    await asyncio.sleep(0.5)

    # Playwright-native filling
    await _fill_phone_if_present(adapter, phone)
    await _fill_text_inputs(adapter, responses.get("input_field", {}))
    await _fill_dropdowns(adapter, responses.get("dropdown", {}), experience_years)
    await _fill_radio_buttons(adapter, responses.get("radio", {}), experience_years)

    # JS fallback for fields Playwright missed
    await _fill_fields_via_js(adapter, responses.get("input_field", {}), phone)
