const form = document.getElementById("form");
const msg = document.getElementById("msg");
const button = document.getElementById("go");

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  msg.textContent = "";
  button.disabled = true;
  try {
    const res = await fetch("/api/login", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ password: document.getElementById("pw").value }) });
    const data = await res.json().catch(() => ({}));
    if (res.ok) { location.href = "/"; return; }
    msg.textContent = data.error || "Could not sign in. Try again.";
  } catch {
    msg.textContent = "Cannot reach the server. Check your connection.";
  } finally { button.disabled = false; }
});
