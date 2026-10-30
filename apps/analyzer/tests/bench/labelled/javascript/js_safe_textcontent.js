function showGreeting() {
  const name = decodeURIComponent(location.hash.slice(1));
  document.getElementById("greeting").textContent = "Hello, " + name;
}

window.addEventListener("load", showGreeting);
