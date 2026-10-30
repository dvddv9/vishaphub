function showGreeting() {
  const name = decodeURIComponent(location.hash.slice(1));
  document.getElementById("greeting").innerHTML = "Hello, " + name;
}

window.addEventListener("load", showGreeting);
