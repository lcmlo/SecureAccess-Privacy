'use strict';
// Melhoria progressiva: os formulários e a navegação funcionam sem JavaScript.
(() => {
    const birthInput = document.querySelector('[data-birth-date]');
    const ageOutput = document.querySelector('[data-age-output]');
    const ageDisplays = [...document.querySelectorAll('[data-age-display]')];
    if (!birthInput && !ageDisplays.length) return;

    function ageFromDate(value, today) {
        if (!/^[0-9]{4}-[0-9]{2}-[0-9]{2}$/.test(value)) return null;
        const [year, month, day] = value.split('-').map(Number);
        const birth = new Date(0);
        birth.setUTCHours(0, 0, 0, 0);
        birth.setUTCFullYear(year, month - 1, day);
        if (year < 1 || birth.getUTCFullYear() !== year || birth.getUTCMonth() !== month - 1 || birth.getUTCDate() !== day) return null;
        const todayYear = today.getUTCFullYear();
        const todayMonth = today.getUTCMonth() + 1;
        const todayDay = today.getUTCDate();
        if (value > today.toISOString().slice(0, 10)) return null;
        // 29/02: o aniversário ocorre em 01/03 nos anos não bissextos, como em Python.
        return todayYear - year - Number(todayMonth < month || (todayMonth === month && todayDay < day));
    }
    const formatAge = (age) => age === null ? 'Não indicada' : `${age} ${age === 1 ? 'ano' : 'anos'}`;
    function refreshAge() {
        const today = new Date();
        if (birthInput) {
            birthInput.max = today.toISOString().slice(0, 10);
            const age = ageFromDate(birthInput.value, today);
            birthInput.setCustomValidity(birthInput.value && age === null ? 'Introduza uma data de nascimento válida, sem ser futura.' : '');
            if (ageOutput) ageOutput.value = formatAge(age);
        }
        ageDisplays.forEach((display) => {
            display.textContent = formatAge(ageFromDate(display.dataset.birthDateValue, today));
        });
    }
    let midnightTimer;
    function refreshAndSchedule() {
        refreshAge();
        clearTimeout(midnightTimer);
        const now = new Date();
        const nextMidnight = Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate() + 1);
        midnightTimer = setTimeout(refreshAndSchedule, nextMidnight - now.getTime() + 100);
    }
    if (birthInput) {
        birthInput.addEventListener('input', refreshAge);
        birthInput.addEventListener('change', refreshAge);
    }
    document.addEventListener('visibilitychange', () => {
        if (!document.hidden) refreshAndSchedule();
    });
    window.addEventListener('focus', refreshAndSchedule);
    refreshAndSchedule();
})();
document.querySelectorAll('[data-navbar-avatar]').forEach((image) => {
    // O ícone de utilizador permanece por baixo da imagem como fallback.
    image.addEventListener('error', () => image.remove(), { once: true });
    if (image.complete && image.naturalWidth === 0) image.remove();
});
const menuToggle = document.querySelector('.menu-toggle');
if (menuToggle) {
    document.body.classList.add('nav-ready');
    menuToggle.addEventListener('click', () => {
        const open = document.body.classList.toggle('nav-open');
        menuToggle.setAttribute('aria-expanded', String(open));
    });
    document.addEventListener('keydown', (event) => {
        if (event.key === 'Escape' && document.body.classList.contains('nav-open')) {
            document.body.classList.remove('nav-open');
            menuToggle.setAttribute('aria-expanded', 'false');
            menuToggle.focus();
        }
    });
}
document.querySelectorAll('input[type="password"]').forEach((input, index) => {
    const wrapper = document.createElement('span');
    wrapper.className = 'password-field';
    input.before(wrapper);
    wrapper.append(input);
    if (!input.id) input.id = `password-field-${index}`;
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'password-toggle';
    button.setAttribute('aria-controls', input.id);
    button.setAttribute('aria-label', 'Mostrar palavra-passe');
    button.setAttribute('aria-pressed', 'false');
    button.title = 'Mostrar palavra-passe';
    button.innerHTML = '<svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12Z"/><circle cx="12" cy="12" r="3"/><path class="eye-slash" d="m3 3 18 18"/></svg>';
    // Keep the input focused when the control is pressed with a mouse.
    button.addEventListener('mousedown', (event) => event.preventDefault());
    button.addEventListener('click', () => {
        const start = input.selectionStart;
        const end = input.selectionEnd;
        const direction = input.selectionDirection;
        const visible = input.type === 'password';
        input.type = visible ? 'text' : 'password';
        button.setAttribute('aria-pressed', String(visible));
        const label = visible ? 'Ocultar palavra-passe' : 'Mostrar palavra-passe';
        button.setAttribute('aria-label', label);
        button.title = label;
        input.focus({ preventScroll: true });
        if (start !== null && end !== null) input.setSelectionRange(start, end, direction);
    });
    wrapper.append(button);
});
const password = document.querySelector('input[name="password"][autocomplete="new-password"]');
const confirmation = document.querySelector('input[name="password_confirmation"]');
if (password && confirmation) {
    const validatePassword = () => confirmation.setCustomValidity(
        password.value === confirmation.value ? '' : 'A confirmação da palavra-passe não coincide.');
    password.addEventListener('input', validatePassword);
    confirmation.addEventListener('input', validatePassword);
}
document.querySelectorAll('[data-dismiss-alert]').forEach((button) => {
    button.addEventListener('click', () => button.closest('.flash').remove());
});
