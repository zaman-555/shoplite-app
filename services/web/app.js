const productsEl = document.querySelector("#products");
const ordersEl = document.querySelector("#orders");
const productMessage = document.querySelector("#product-message");
const orderMessage = document.querySelector("#order-message");
const refreshButton = document.querySelector("#refresh");
const lookupForm = document.querySelector("#lookup");

const STORAGE_KEY = "shoplite.orders";
const tracked = new Map();
const polling = new Set();

function money(value) {
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(value);
}

function detailMessage(body, fallback) {
  if (body && typeof body.detail === "string") return body.detail;
  return fallback;
}

function loadStored() {
  try {
    const saved = JSON.parse(localStorage.getItem(STORAGE_KEY) || "[]");
    saved.forEach((order) => tracked.set(order.id, order));
  } catch {
    tracked.clear();
  }
}

function saveStored() {
  localStorage.setItem(STORAGE_KEY, JSON.stringify([...tracked.values()]));
}

function renderProducts(products) {
  productsEl.replaceChildren();
  if (products.length === 0) {
    const empty = document.createElement("p");
    empty.className = "empty";
    empty.textContent = "No products are available.";
    productsEl.append(empty);
    return;
  }

  products.forEach((product) => {
    const card = document.createElement("article");
    card.className = "product";

    const title = document.createElement("h3");
    title.textContent = product.name;

    const meta = document.createElement("p");
    meta.className = "meta";
    meta.textContent = `${money(product.price)} · ${product.stock} in stock`;

    const form = document.createElement("form");
    form.className = "order-form";

    const label = document.createElement("label");
    const inputId = `qty-${product.id}`;
    label.htmlFor = inputId;
    label.textContent = "Quantity";

    const input = document.createElement("input");
    input.id = inputId;
    input.type = "number";
    input.min = "1";
    input.value = "1";
    if (product.stock > 0) input.max = String(product.stock);
    input.required = true;

    const button = document.createElement("button");
    button.type = "submit";
    button.textContent = "Place order";
    button.disabled = product.stock < 1;

    form.append(label, input, button);
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      placeOrder(product.id, Number(input.value), button);
    });

    card.append(title, meta, form);
    productsEl.append(card);
  });
}

function renderOrders() {
  ordersEl.replaceChildren();
  const orders = [...tracked.values()].sort((a, b) => b.id - a.id);
  if (orders.length === 0) {
    const empty = document.createElement("p");
    empty.className = "empty";
    empty.textContent = "Orders you place will show up here.";
    ordersEl.append(empty);
    return;
  }

  orders.forEach((order) => {
    const card = document.createElement("article");
    card.className = "order";

    const top = document.createElement("div");
    top.className = "order-top";

    const title = document.createElement("h3");
    title.textContent = `Order ${order.id}`;

    const status = document.createElement("span");
    status.className = `status ${String(order.status).toLowerCase()}`;
    status.textContent = order.status;

    const meta = document.createElement("p");
    meta.className = "meta";
    meta.textContent = `Product ${order.product_id} · quantity ${order.quantity}`;

    top.append(title, status);
    card.append(top, meta);
    ordersEl.append(card);
  });
}

async function loadProducts() {
  productMessage.textContent = "";
  try {
    const response = await fetch("/products");
    const body = await response.json().catch(() => null);
    if (!response.ok) throw new Error(detailMessage(body, "Could not load products"));
    renderProducts(body);
  } catch (error) {
    productMessage.textContent = error.message;
  }
}

async function placeOrder(productId, quantity, button) {
  productMessage.textContent = "";
  if (!Number.isInteger(quantity) || quantity < 1) {
    productMessage.textContent = "Enter a quantity of at least 1.";
    return;
  }
  button.disabled = true;
  try {
    const response = await fetch("/orders", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ product_id: productId, quantity }),
    });
    const body = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(detailMessage(body, "Could not place the order"));
    tracked.set(body.id, body);
    saveStored();
    renderOrders();
    pollOrder(body.id);
  } catch (error) {
    productMessage.textContent = error.message;
  } finally {
    button.disabled = false;
  }
}

async function viewOrder(orderId) {
  orderMessage.textContent = "";
  const response = await fetch(`/orders/${orderId}`);
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(detailMessage(body, "Order not found"));
  tracked.set(body.id, body);
  saveStored();
  renderOrders();
  if (body.status === "PENDING" || body.status === "PROCESSING") pollOrder(body.id);
}

function pollOrder(orderId) {
  if (polling.has(orderId)) return;
  polling.add(orderId);
  const started = Date.now();

  const timer = setInterval(async () => {
    try {
      const response = await fetch(`/orders/${orderId}`);
      if (!response.ok) return;
      const order = await response.json();
      tracked.set(order.id, order);
      saveStored();
      renderOrders();
      const finished = order.status === "COMPLETED" || order.status === "FAILED";
      if (finished || Date.now() - started > 60000) {
        clearInterval(timer);
        polling.delete(orderId);
        if (finished) loadProducts();
      }
    } catch {
      // The next tick retries while the order is still open.
    }
  }, 1000);
}

refreshButton.addEventListener("click", loadProducts);

lookupForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const orderId = Number(document.querySelector("#order-id").value);
  try {
    await viewOrder(orderId);
  } catch (error) {
    orderMessage.textContent = error.message;
  }
});

loadStored();
renderOrders();
[...tracked.values()]
  .filter((order) => order.status === "PENDING" || order.status === "PROCESSING")
  .forEach((order) => pollOrder(order.id));
loadProducts();
