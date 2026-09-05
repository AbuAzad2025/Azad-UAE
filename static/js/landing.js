// Smooth scroll
document.querySelectorAll('a[href^="#"]').forEach((anchor) => {
	anchor.addEventListener("click", function (e) {
		e.preventDefault();
		const target = document.querySelector(this.getAttribute("href"));
		if (target) {
			target.scrollIntoView({ behavior: "smooth" });
		}
	});
});

// Animate on scroll
const observerOptions = {
	threshold: 0.1,
	rootMargin: "0px 0px -50px 0px",
};

const observer = new IntersectionObserver((entries) => {
	entries.forEach((entry) => {
		if (entry.isIntersecting) {
			entry.target.style.opacity = "1";
			entry.target.style.transform = "translateY(0)";
		}
	});
}, observerOptions);

document.querySelectorAll(".feature-card, .price-card").forEach((el) => {
	el.style.opacity = "0";
	el.style.transform = "translateY(50px)";
	el.style.transition = "all 0.8s ease-out";
	observer.observe(el);
});

const openBtn = document.getElementById("landingSidebarOpen");
const closeBtn = document.getElementById("landingSidebarClose");
const backdrop = document.getElementById("landingSidebarBackdrop");
const sidebar = document.getElementById("landingSidebar");
const openSidebar = () => {
	document.body.classList.add("landing-sidebar-open");
	sidebar.setAttribute("aria-hidden", "false");
};
const closeSidebar = () => {
	document.body.classList.remove("landing-sidebar-open");
	sidebar.setAttribute("aria-hidden", "true");
};
if (openBtn) openBtn.addEventListener("click", openSidebar);
if (closeBtn) closeBtn.addEventListener("click", closeSidebar);

// ── Landing Pages Flash Auto-Dismiss (.azad-flash-item) ──
// Logout / success flashes previously stayed forever on landing pages
// because landing.html loads landing.js only (no base-helpers.js).
document.querySelectorAll(".azad-flash-item").forEach((el) => {
	if (el.dataset.azadFlashDismiss) return;
	el.dataset.azadFlashDismiss = "1";

	const isDanger = el.classList.contains("azad-flash-item--danger");
	const isWarning = el.classList.contains("azad-flash-item--warning");
	const duration = isDanger ? 9000 : isWarning ? 7000 : 3500;

	el.style.position = "relative";
	el.style.overflow = "hidden";
	const bar = document.createElement("span");
	bar.style.cssText =
		"position:absolute; inset:auto 0 0 0; height:3px; background:currentColor; opacity:0.35; transform-origin:left center; transform:scaleX(1); transition:transform " +
		Math.max(150, duration - 300) +
		"ms linear;";
	requestAnimationFrame(() => (bar.style.transform = "scaleX(0.01)"));
	el.appendChild(bar);

	setTimeout(() => {
		el.style.transition = "opacity 0.35s ease, transform 0.35s ease";
		el.style.opacity = "0";
		el.style.transform = "translateY(-6px)";
		setTimeout(() => el.remove(), 400);
	}, duration);
});
if (backdrop) backdrop.addEventListener("click", closeSidebar);
document.querySelectorAll(".landing-scroll-link").forEach((a) => {
	a.addEventListener("click", () => closeSidebar());
});
