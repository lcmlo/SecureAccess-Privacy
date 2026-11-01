'use strict';
// Carregado antes dos estilos: apenas a preferência visual é guardada no navegador.
(() => {
    const storageKey = 'secureaccess-theme';
    const root = document.documentElement;
    const system = window.matchMedia('(prefers-color-scheme: dark)');
    const labels = { light: 'Claro', dark: 'Escuro', system: 'Automático' };
    const icons = { light: 'sun', dark: 'moon', system: 'monitor' };
    let preference = 'system';
    try {
        const stored = localStorage.getItem(storageKey);
        if (Object.hasOwn(labels, stored)) preference = stored;
    } catch { /* O tema continua funcional quando o armazenamento está bloqueado. */ }

    function applyTheme() {
        root.dataset.theme = preference === 'system' ? (system.matches ? 'dark' : 'light') : preference;
        root.dataset.themePreference = preference;
        document.querySelectorAll('[data-theme-picker]').forEach((picker) => {
            const toggle = picker.querySelector('[data-theme-toggle]');
            toggle.setAttribute('aria-label', `Tema: ${labels[preference]}. Escolher tema`);
            toggle.title = `Tema: ${labels[preference]}`;
            picker.querySelector('[data-theme-icon]').setAttribute('href', `#theme-icon-${icons[preference]}`);
            picker.querySelectorAll('[data-theme-choice]').forEach((option) => {
                option.setAttribute('aria-checked', String(option.dataset.themeChoice === preference));
            });
        });
    }
    applyTheme();
    system.addEventListener('change', () => {
        if (preference === 'system') applyTheme();
    });
    window.addEventListener('storage', (event) => {
        if (event.key === storageKey || event.key === null) {
            preference = Object.hasOwn(labels, event.newValue) ? event.newValue : 'system';
            applyTheme();
        }
    });

    document.addEventListener('DOMContentLoaded', () => {
        document.querySelectorAll('[data-theme-picker]').forEach((picker) => {
            const toggle = picker.querySelector('[data-theme-toggle]');
            const menu = picker.querySelector('[data-theme-menu]');
            const options = [...picker.querySelectorAll('[data-theme-choice]')];
            function close(restoreFocus = false) {
                menu.hidden = true;
                toggle.setAttribute('aria-expanded', 'false');
                if (restoreFocus) toggle.focus();
            }
            function open() {
                menu.hidden = false;
                toggle.setAttribute('aria-expanded', 'true');
                options.find((option) => option.dataset.themeChoice === preference).focus();
            }
            toggle.addEventListener('click', () => menu.hidden ? open() : close());
            toggle.addEventListener('keydown', (event) => {
                if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
                    event.preventDefault();
                    open();
                }
            });
            options.forEach((option) => option.addEventListener('click', () => {
                preference = option.dataset.themeChoice;
                try { localStorage.setItem(storageKey, preference); } catch { /* Sessão sem persistência. */ }
                applyTheme();
                close(true);
            }));
            menu.addEventListener('keydown', (event) => {
                const index = options.indexOf(document.activeElement);
                let next;
                if (event.key === 'ArrowDown') next = (index + 1) % options.length;
                if (event.key === 'ArrowUp') next = (index + options.length - 1) % options.length;
                if (event.key === 'Home') next = 0;
                if (event.key === 'End') next = options.length - 1;
                if (next !== undefined) {
                    event.preventDefault();
                    options[next].focus();
                }
                if (event.key === 'Tab') close();
            });
            picker.addEventListener('keydown', (event) => {
                if (event.key === 'Escape' && !menu.hidden) {
                    event.preventDefault();
                    event.stopPropagation();
                    close(true);
                }
            });
            document.addEventListener('click', (event) => {
                if (!picker.contains(event.target)) close();
            });
            picker.addEventListener('focusout', (event) => {
                if (!picker.contains(event.relatedTarget)) close();
            });
            picker.hidden = false;
        });
        applyTheme();
    });
})();
