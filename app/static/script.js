/* =============================================
   RetailIQ — Landing Page Scripts
   ============================================= */

document.addEventListener('DOMContentLoaded', () => {

  /* ---------- THEME TOGGLE ---------- */
  const html = document.documentElement;
  const themeToggle = document.getElementById('themeToggle');
  const stored = localStorage.getItem('retailiq-theme');
  if (stored) html.setAttribute('data-theme', stored);

  themeToggle.addEventListener('click', () => {
    const next = html.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
    html.setAttribute('data-theme', next);
    localStorage.setItem('retailiq-theme', next);
  });

  /* ---------- NAVBAR SCROLL ---------- */
  const navbar = document.getElementById('navbar');
  const onScroll = () => {
    navbar.classList.toggle('scrolled', window.scrollY > 20);
  };
  window.addEventListener('scroll', onScroll, { passive: true });
  onScroll();

  /* ---------- MOBILE MENU ---------- */
  const mobileMenuBtn = document.getElementById('mobileMenuBtn');
  const navLinks = document.getElementById('navLinks');
  mobileMenuBtn.addEventListener('click', () => {
    navLinks.classList.toggle('open');
    mobileMenuBtn.classList.toggle('open');
  });
  navLinks.querySelectorAll('a').forEach(link => {
    link.addEventListener('click', () => {
      navLinks.classList.remove('open');
      mobileMenuBtn.classList.remove('open');
    });
  });

  /* ---------- SMOOTH SCROLL ---------- */
  document.querySelectorAll('a[href^="#"]').forEach(anchor => {
    anchor.addEventListener('click', (e) => {
      const target = document.querySelector(anchor.getAttribute('href'));
      if (target) {
        e.preventDefault();
        target.scrollIntoView({ behavior: 'smooth' });
      }
    });
  });

  /* ---------- SCROLL ANIMATIONS ---------- */
  const animElements = document.querySelectorAll('.animate-on-scroll');
  const observer = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          entry.target.classList.add('visible');
          observer.unobserve(entry.target);
        }
      });
    },
    { threshold: 0.1, rootMargin: '0px 0px -40px 0px' }
  );
  animElements.forEach((el, i) => {
    el.style.transitionDelay = `${Math.min(i % 6, 3) * 80}ms`;
    observer.observe(el);
  });

  /* ---------- FAQ ACCORDION ---------- */
  document.querySelectorAll('.faq-question').forEach(btn => {
    btn.addEventListener('click', () => {
      const item = btn.parentElement;
      const isOpen = item.classList.contains('open');
      document.querySelectorAll('.faq-item.open').forEach(openItem => {
        openItem.classList.remove('open');
        openItem.querySelector('.faq-question').setAttribute('aria-expanded', 'false');
      });
      if (!isOpen) {
        item.classList.add('open');
        btn.setAttribute('aria-expanded', 'true');
      }
    });
  });

  /* ---------- PRICING TOGGLE ---------- */
  const pricingToggle = document.getElementById('pricingToggle');
  const toggleLabels = document.querySelectorAll('.pricing-toggle-label');
  const priceValues = document.querySelectorAll('.price-value');
  const periods = document.querySelectorAll('.period');
  const annualNotes = document.querySelectorAll('.pricing-annual-note');
  let isAnnual = false;

  // Set initial state
  toggleLabels[0].classList.add('active');

  if (pricingToggle) {
    pricingToggle.addEventListener('click', () => {
      isAnnual = !isAnnual;
      pricingToggle.classList.toggle('active', isAnnual);

      toggleLabels.forEach(label => {
        const period = label.dataset.period;
        label.classList.toggle('active', (isAnnual && period === 'annual') || (!isAnnual && period === 'monthly'));
      });

      priceValues.forEach(el => {
        const val = isAnnual ? el.dataset.annual : el.dataset.monthly;
        el.textContent = val;
      });

      periods.forEach(el => {
        el.textContent = isAnnual ? el.dataset.annual : el.dataset.monthly;
      });

      annualNotes.forEach(el => {
        el.hidden = !isAnnual;
      });
    });
  }

  /* ---------- DEMO AI ITEMS ANIMATION ---------- */
  const demoItems = document.querySelectorAll('.demo-ai-item');
  if (demoItems.length > 0) {
    const demoObserver = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            const items = entry.target.querySelectorAll('.demo-ai-item');
            items.forEach((item, i) => {
              const delay = parseInt(item.dataset.delay || '0', 10);
              setTimeout(() => {
                item.classList.add('visible');
              }, 300 + delay);
            });
            demoObserver.unobserve(entry.target);
          }
        });
      },
      { threshold: 0.3 }
    );
    const demoBody = document.getElementById('demoAiBody');
    if (demoBody) demoObserver.observe(demoBody);
  }

  /* ---------- COUNTER ANIMATION ---------- */
  const counterEl = document.querySelector('.trust-text strong');
  if (counterEl) {
    const targetText = counterEl.textContent;
    const match = targetText.match(/(\d+)/);
    if (match) {
      const target = parseInt(match[1], 10);
      let current = 0;
      const counterObserver = new IntersectionObserver((entries) => {
        if (entries[0].isIntersecting) {
          const step = Math.ceil(target / 40);
          const interval = setInterval(() => {
            current += step;
            if (current >= target) {
              current = target;
              clearInterval(interval);
            }
            counterEl.textContent = targetText.replace(/\d+/, current);
          }, 30);
          counterObserver.disconnect();
        }
      }, { threshold: 0.5 });
      counterObserver.observe(counterEl);
    }
  }
});
