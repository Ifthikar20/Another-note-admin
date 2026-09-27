// The stored theme (localStorage "admin.theme": "light", "dark" or "system"), applied
// before first paint so a dark reload never flashes white. Mirrors src/lib/theme.ts.
(function () {
  try {
    var pref = localStorage.getItem("admin.theme") || "system";
    var dark = pref === "dark" || (pref === "system" && window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches);
    if (dark) document.documentElement.classList.add("dark");
    document.documentElement.style.colorScheme = dark ? "dark" : "light";
  } catch (e) {
    /* storage blocked: light */
  }
})();
