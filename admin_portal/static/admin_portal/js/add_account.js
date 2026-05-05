document.addEventListener('DOMContentLoaded', () => {
  const roleSelect = document.getElementById('roleSelect');
  if (!roleSelect) return;

  const customerFields = document.querySelector('.customer-fields');
  const staffAdminFields = document.querySelectorAll('.staff-admin-field');
  const usernameInput = document.getElementById('usernameInput');
  const emailInput = document.getElementById('emailInput');
  const nameInput = document.getElementById('nameInput');
  const contactInput = document.getElementById('contactInput');
  const addressInput = document.getElementById('addressInput');
  const roleHelp = document.getElementById('roleHelp');

  function syncRoleFields() {
    const isCustomer = roleSelect.value === 'customer';
    customerFields.classList.toggle('d-none', !isCustomer);
    staffAdminFields.forEach((field) => field.classList.toggle('d-none', isCustomer));
    usernameInput.required = !isCustomer;
    emailInput.required = isCustomer;
    nameInput.required = isCustomer;
    contactInput.required = isCustomer;
    addressInput.required = isCustomer;
    roleHelp.textContent = isCustomer
      ? 'Customer accounts use their email as the login and are linked to a customer profile.'
      : 'Staff accounts can access staff workflows. Admin accounts can manage reports, pricing, inventory rules, and accounts.';
  }

  roleSelect.addEventListener('change', syncRoleFields);
  syncRoleFields();
});
