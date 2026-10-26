'use strict';
// Mantém apenas um formulário de gestão de conta expandido de cada vez.
const accountPanels = [...document.querySelectorAll('td details')];
accountPanels.forEach((panel) => {
    panel.addEventListener('toggle', () => {
        if (panel.open) {
            accountPanels.filter((other) => other !== panel).forEach((other) => { other.open = false; });
        }
    });
});
