// Theme bootstrap (formerly inline at the top of <body>).
// Runs before the SPA renders to avoid a flash of the wrong theme.
(function () {
  var t = localStorage.getItem('pergen-theme') || 'dark';
  document.body.classList.add(t === 'light' ? 'theme-light' : 'theme-dark');
})();
