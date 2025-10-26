// Handles show/hide behaviour for password inputs that have an adjacent
// button with the class `.toggle-password`.

const PASSWORD_VISIBLE_TYPE = "text";
const PASSWORD_HIDDEN_TYPE = "password";
const TOGGLE_ACTIVE_ATTR = "data-password-visible";

function resolveInputElement(toggleButton) {
  const selector = toggleButton.getAttribute("data-target");
  if (selector) {
    const target = document.querySelector(selector);
    if (target instanceof HTMLInputElement) {
      return target;
    }
  }

  let sibling = toggleButton.previousElementSibling;
  while (sibling) {
    if (sibling instanceof HTMLInputElement) {
      return sibling;
    }
    sibling = sibling.previousElementSibling;
  }

  return null;
}

function updateButtonState(button, isVisible) {
  button.setAttribute(TOGGLE_ACTIVE_ATTR, isVisible ? "true" : "false");
  button.setAttribute("aria-pressed", isVisible ? "true" : "false");
  const label = button.getAttribute("data-label-visible") || "הסתר";
  const hiddenLabel = button.getAttribute("data-label-hidden") || "הצג";
  button.setAttribute("aria-label", isVisible ? label : hiddenLabel);
}

function bindToggle(button) {
  const input = resolveInputElement(button);
  if (!input) {
    console.warn("password-toggle: target input not found", button);
    return;
  }

  const update = (forceVisible) => {
    const nextVisible = typeof forceVisible === "boolean"
      ? forceVisible
      : input.type === PASSWORD_HIDDEN_TYPE;
    input.type = nextVisible ? PASSWORD_VISIBLE_TYPE : PASSWORD_HIDDEN_TYPE;
    updateButtonState(button, nextVisible);
  };

  button.addEventListener("click", (event) => {
    event.preventDefault();
    update();
  });

  if (button.matches("[data-sync='true']")) {
    input.addEventListener("input", () => {
      if (!input.value) {
        update(false);
      }
    });
  }

  update(false);
}

function initPasswordToggles() {
  const toggles = document.querySelectorAll(".toggle-password");
  toggles.forEach(bindToggle);
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", initPasswordToggles);
} else {
  initPasswordToggles();
}
