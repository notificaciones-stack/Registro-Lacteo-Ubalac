document.addEventListener('DOMContentLoaded', () => {
  const category = document.querySelector('[name="fiscal_category"]');
  if (!category) return;
  const documents = ['document_type', 'document_number'].map((name) => document.querySelector(`[name="${name}"]`));
  const products = [...document.querySelectorAll('input[name="products"]')];
  const update = () => {
    documents.forEach((field) => {
      if (!field) return;
      field.required = category.value !== 'SMALL';
      field.setAttribute('aria-required', String(field.required));
    });
    products.forEach((product) => {
      const price = document.querySelector(`[name="price_${product.value}"]`);
      if (price) {
        price.disabled = !product.checked;
        price.required = product.checked;
        price.setAttribute('aria-required', String(product.checked));
      }
    });
  };
  category.addEventListener('change', update);
  products.forEach((product) => product.addEventListener('change', update));
  update();
});
