document.querySelectorAll('[data-job-assignment]').forEach(form => {
    const department = form.querySelector('[data-department]');
    const position = form.querySelector('[data-position]');
    const options = Array.from(position.options).slice(1).map(option => option.cloneNode(true));
    function update() {
        const previous = position.value;
        position.replaceChildren(new Option('Selecionar', ''));
        options.filter(option => option.dataset.departmentId === department.value)
            .forEach(option => position.append(option.cloneNode(true)));
        position.value = Array.from(position.options).some(option => option.value === previous) ? previous : '';
    }
    department.addEventListener('change', update);
    update();
});
