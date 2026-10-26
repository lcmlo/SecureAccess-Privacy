'use strict';
// Validação acessível da seleção de categorias na exportação.
const categories = [...document.querySelectorAll('input[name="categories"]')];
function validateCategories() {
    if (categories.length) {
        categories[0].setCustomValidity(categories.some((field) => field.checked)
            ? '' : 'Selecione pelo menos uma categoria para exportar.');
    }
}
categories.forEach((field) => field.addEventListener('change', validateCategories));
validateCategories();
