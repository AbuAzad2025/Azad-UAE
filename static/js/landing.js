// Smooth scroll
document.querySelectorAll('a[href^=\"#\"]').forEach(anchor => {
    anchor.addEventListener('click', function (e) {
        e.preventDefault();
        const target = document.querySelector(this.getAttribute('href'));
        if (target) {
            target.scrollIntoView({ behavior: 'smooth' });
        }
    });
});

// Animate on scroll
const observerOptions = {
    threshold: 0.1,
    rootMargin: '0px 0px -50px 0px'
};

const observer = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
        if (entry.isIntersecting) {
            entry.target.style.opacity = '1';
            entry.target.style.transform = 'translateY(0)';
        }
    });
}, observerOptions);

document.querySelectorAll('.feature-card, .price-card').forEach(el => {
    el.style.opacity = '0';
    el.style.transform = 'translateY(50px)';
    el.style.transition = 'all 0.8s ease-out';
    observer.observe(el);
});

const openBtn = document.getElementById('landingSidebarOpen');
const closeBtn = document.getElementById('landingSidebarClose');
const backdrop = document.getElementById('landingSidebarBackdrop');
const sidebar = document.getElementById('landingSidebar');
const openSidebar = () => {
    document.body.classList.add('landing-sidebar-open');
    sidebar.setAttribute('aria-hidden', 'false');
};
const closeSidebar = () => {
    document.body.classList.remove('landing-sidebar-open');
    sidebar.setAttribute('aria-hidden', 'true');
};
if (openBtn) openBtn.addEventListener('click', openSidebar);
if (closeBtn) closeBtn.addEventListener('click', closeSidebar);
if (backdrop) backdrop.addEventListener('click', closeSidebar);
document.querySelectorAll('.landing-scroll-link').forEach(a => {
    a.addEventListener('click', () => closeSidebar());
});
