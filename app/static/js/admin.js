'use strict';
// Mantém apenas um formulário de gestão de conta expandido de cada vez.
document.querySelectorAll('[data-role-dialog]').forEach((link) => {
    const dialog = document.getElementById(link.dataset.roleDialog);
    if (!dialog || typeof dialog.showModal !== 'function') return;
    link.addEventListener('click', (event) => {
        event.preventDefault();
        dialog.showModal();
    });
    dialog.querySelector('[data-dialog-close]').addEventListener('click', (event) => {
        event.preventDefault();
        dialog.close();
    });
    dialog.addEventListener('close', () => dialog.querySelector('form').reset());
    dialog.addEventListener('click', (event) => {
        if (event.target === dialog) {
            const box = dialog.getBoundingClientRect();
            if (event.clientX < box.left || event.clientX > box.right || event.clientY < box.top || event.clientY > box.bottom) dialog.close();
        }
    });
});
const accountPanels = [...document.querySelectorAll('td details')];
accountPanels.forEach((panel) => {
    panel.addEventListener('toggle', () => {
        if (panel.open) {
            accountPanels.filter((other) => other !== panel).forEach((other) => { other.open = false; });
        }
    });
});
