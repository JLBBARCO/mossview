export function initializeNavigation() {
  const header = document.querySelector(".header-inner");
  const toggle = document.querySelector(".nav-toggle");
  const navigation = document.querySelector("#main-navigation");

  if (!header || !toggle || !navigation) return;

  const mobile = window.matchMedia("(max-width: 740px)");
  const label = toggle.querySelector(".nav-toggle-label");

  const setOpen = (open) => {
    header.classList.toggle("nav-open", open);
    toggle.setAttribute("aria-expanded", String(open));
    toggle.setAttribute("aria-label", open ? "Fechar navegação" : "Abrir navegação");
    if (label) label.textContent = open ? "Fechar" : "Menu";
  };

  const close = (restoreFocus = false) => {
    setOpen(false);
    if (restoreFocus) toggle.focus();
  };

  toggle.addEventListener("click", () => {
    setOpen(toggle.getAttribute("aria-expanded") !== "true");
  });

  navigation.addEventListener("click", (event) => {
    if (mobile.matches && event.target instanceof Element && event.target.closest("a")) {
      close();
    }
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && header.classList.contains("nav-open")) {
      close(true);
    }
  });

  mobile.addEventListener("change", (event) => {
    if (!event.matches) close();
  });

  document.documentElement.classList.add("nav-js-ready");
}
