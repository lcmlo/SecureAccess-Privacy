'use strict';
// Melhoria progressiva: os formulários e a navegação funcionam sem JavaScript.
document.querySelectorAll('[data-dismiss-alert]').forEach((button) => {
    button.addEventListener('click', () => button.closest('.flash').remove());
});
