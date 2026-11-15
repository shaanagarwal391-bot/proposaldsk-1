document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll("form").forEach(form => {
    form.addEventListener("submit", () => {
      const button = form.querySelector('button[type="submit"], button:not([type])');
      if (button && !form.hasAttribute("onsubmit")) {
        button.dataset.originalText = button.textContent;
        button.textContent = "Saving…";
      }
    });
  });

  const feeList = document.getElementById("service-fee-list");
  const currencySelect = document.querySelector('select[name="currency"]');
  const amountField = document.getElementById("proposal-amount");
  const currencySymbols = { INR: "₹", USD: "$", EUR: "€", GBP: "£" };

  // Built-in scope suggestions: typing a recognised service name fills its scope.
  // Users can edit the suggested text at any time.
  const serviceScopeSuggestions = [
    { keys: ["trademark", "trade mark", "trademark registration", "brand registration"], scope: "Conduct a preliminary trademark search and review the proposed mark and relevant class(es); advise on registrability and documentation; prepare and file the trademark application with the Indian Trade Marks Registry; share the application acknowledgement and monitor the application status. Examination reports, hearings, oppositions, renewals and other post-filing work are included only if separately agreed." },
    { keys: ["trademark search", "trade mark search", "brand search"], scope: "Search the relevant Indian Trade Marks Registry records for identical or deceptively similar marks in the proposed class(es); review the search results and provide a summary of potential conflicts and practical filing considerations. This is a preliminary assessment and does not guarantee registration." },
    { keys: ["trademark objection", "reply to trademark objection", "trade mark objection"], scope: "Review the examination report issued by the Indian Trade Marks Registry; discuss the objections and available responses; prepare and file a written reply with supporting documents and evidence based on information provided by the client. Show-cause hearing attendance or further proceedings are included only if expressly agreed." },
    { keys: ["trademark renewal", "trade mark renewal"], scope: "Review the trademark registration details and renewal due date; prepare and file the prescribed renewal request with the Indian Trade Marks Registry; provide the filing acknowledgement and update the client on the status. Restoration, late fees or contested proceedings, if applicable, are additional unless agreed." },
    { keys: ["copyright registration", "copyright"], scope: "Review the work and ownership details supplied by the client; prepare the prescribed copyright application and supporting documents; file the application with the Copyright Office and share the acknowledgement. Replies to objections, hearings or ownership disputes are outside this scope unless separately agreed." },
    { keys: ["gst registration", "goods and services tax registration"], scope: "Review the applicant's details and supporting documents; prepare and submit the GST registration application on the GST portal; respond to routine clarification requests based on documents provided; and share the GST registration certificate once issued. Additional registrations, amendments or appeals are excluded unless agreed." },
    { keys: ["gst return", "gstr-1", "gstr 1", "gstr-3b", "gstr 3b", "gst filing"], scope: "Compile and review sales, purchase and tax information provided by the client; prepare the applicable GST returns for the agreed tax periods; reconcile relevant figures and seek clarification on discrepancies; file the returns after client approval and share filing acknowledgements. Interest, late fees and historical corrections are excluded unless agreed." },
    { keys: ["company incorporation", "incorporation", "private limited company registration", "llp incorporation"], scope: "Assist with the proposed entity name and incorporation documentation; prepare the applicable incorporation forms and declarations using information supplied by the promoters; submit the forms to the Ministry of Corporate Affairs and coordinate routine resubmissions; share incorporation documents issued by the Registrar. Government fees, stamp duty and third-party charges are additional." },
    { keys: ["roc compliance", "annual roc compliance", "annual filing", "aoc-4", "mgt-7", "mgt-7a"], scope: "Review the company's statutory records and financial information; prepare the applicable annual ROC forms and supporting documents, including AOC-4 and MGT-7/MGT-7A where applicable; file the approved forms with the Registrar of Companies and share acknowledgements. Additional event-based filings and penalties are excluded unless agreed." },
    { keys: ["income tax return", "itr filing", "income tax filing"], scope: "Collect and review the income, deduction, tax payment and financial information provided by the client; prepare the applicable income-tax return and computation; share it for client verification and approval; file the return and provide the acknowledgement. Tax audit, notices, appeals and revised returns are excluded unless separately agreed." },
    { keys: ["dir-3 kyc", "dir 3 kyc", "director kyc"], scope: "Verify the director's identification and contact details and supporting documents; prepare and file the applicable DIR-3 KYC form with the Ministry of Corporate Affairs; and share the filing acknowledgement. DIN reactivation or additional correction work is excluded unless agreed." },
    { keys: ["tds return", "tds filing", "quarterly tds"], scope: "Review the TDS deduction and challan information provided by the client; reconcile deductee details and tax credits; prepare and file the applicable quarterly TDS statement; and share the filing acknowledgement and any processing updates. Correction statements are additional unless agreed." },
    { keys: ["bookkeeping", "accounting", "accounting services", "accounts maintenance"], scope: "Record and classify transactions based on invoices, bank statements and other records supplied by the client; maintain the agreed books and ledgers; perform routine reconciliations; and provide periodic reports of the books maintained. Audit, certification and tax filings are excluded unless separately agreed." },
    { keys: ["statutory audit", "company audit", "audit"], scope: "Plan and conduct the agreed audit in accordance with applicable statutory requirements; examine books, financial statements and supporting evidence on a test basis; seek explanations and representations from management; and issue the applicable auditor's report. The engagement is subject to agreed audit materiality, records and statutory eligibility." },
    { keys: ["msme registration", "udyam registration", "udyam"], scope: "Review the enterprise details and eligibility information supplied by the client; prepare and submit the Udyam registration application on the official portal; and share the registration acknowledgement or certificate when generated. Eligibility and classification depend on the information and government records." },
    { keys: ["fssai registration", "fssai license", "food license"], scope: "Review the food business activity and applicant documents; identify the applicable FSSAI registration or licence category; prepare and submit the application with supporting documents; and coordinate routine clarification requests. Inspection, renewal, modification and appeal work are excluded unless agreed." },
    { keys: ["import export code", "iec registration", "iec"], scope: "Review the applicant's details and required documents; prepare and submit the Importer-Exporter Code application through the DGFT portal; and share the issued IEC details and acknowledgement. Amendments and other DGFT authorisations are excluded unless agreed." }
  ];

  function findSuggestedScope(serviceName) {
    const name = String(serviceName || "").toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();
    if (!name) return "";
    // Prefer the most specific matching phrase, e.g. 'trademark objection' over 'trademark'.
    const matches = serviceScopeSuggestions
      .flatMap(item => item.keys.map(key => ({ item, key: key.toLowerCase().replace(/[^a-z0-9]+/g, " ").trim() })))
      .filter(entry => name.includes(entry.key) || entry.key.includes(name))
      .sort((a, b) => b.key.length - a.key.length);
    return matches.length ? matches[0].item.scope : "";
  }

  function bindAutomaticScope(nameInput, scopeInput) {
    if (!nameInput || !scopeInput) return;
    const applySuggestion = () => {
      const suggestion = findSuggestedScope(nameInput.value);
      if (!suggestion) return;
      const previousAuto = scopeInput.dataset.autoScope || "";
      if (!scopeInput.value.trim() || scopeInput.value === previousAuto) {
        scopeInput.value = suggestion;
        scopeInput.dataset.autoScope = suggestion;
      }
    };
    nameInput.addEventListener("input", applySuggestion);
    nameInput.addEventListener("change", applySuggestion);
    nameInput.addEventListener("blur", applySuggestion);
  }
  const formatMoney = (value, currency) => {
    const symbol = currencySymbols[currency] || currency + " ";
    return symbol + Number(value || 0).toLocaleString("en-IN", {
      minimumFractionDigits: 2, maximumFractionDigits: 2
    });
  };

  function updateServiceTotals() {
    if (!feeList) return;
    const feeInputs = Array.from(feeList.querySelectorAll(".service-fee-input"));
    const subtotal = feeInputs.reduce((sum, input) => sum + Math.max(0, Number(input.value) || 0), 0);
    const igst = subtotal * 0.18;
    const currency = currencySelect ? currencySelect.value : "INR";
    const subtotalEl = document.getElementById("service-subtotal");
    const igstEl = document.getElementById("service-igst");
    const totalEl = document.getElementById("service-grand-total");
    if (subtotalEl) subtotalEl.textContent = formatMoney(subtotal, currency);
    if (igstEl) igstEl.textContent = formatMoney(igst, currency);
    if (totalEl) totalEl.textContent = formatMoney(subtotal + igst, currency);
    if (amountField) amountField.value = subtotal.toFixed(2);
  }

  function bindServiceRow(row) {
    const nameInput = row.querySelector('input[name="service_name[]"]');
    const feeInput = row.querySelector(".service-fee-input");
    const removeButton = row.querySelector(".remove-service-row");
    bindAutomaticScope(nameInput, row.querySelector('textarea[name="service_scope[]"]'));
    if (feeInput) feeInput.addEventListener("input", updateServiceTotals);
    if (nameInput) {
      nameInput.addEventListener("change", () => {
        const option = Array.from(document.querySelectorAll("#service-catalog-options option"))
          .find(item => item.value.trim().toLowerCase() === nameInput.value.trim().toLowerCase());
        if (option) {
          if (feeInput && option.dataset.amount !== undefined) {
            feeInput.value = Number(option.dataset.amount).toFixed(2);
          }
          const scopeInput = row.querySelector('textarea[name="service_scope[]"]');
          if (scopeInput && option.dataset.scope !== undefined) {
            scopeInput.value = option.dataset.scope;
          }
          updateServiceTotals();
        }
      });
    }
    if (removeButton) {
      removeButton.addEventListener("click", () => {
        if (feeList.querySelectorAll(".service-fee-row").length > 1) {
          row.remove();
          updateServiceTotals();
        } else {
          nameInput.value = "";
          feeInput.value = "0";
          updateServiceTotals();
        }
      });
    }
  }

  if (feeList) {
    feeList.querySelectorAll(".service-fee-row").forEach(bindServiceRow);
    const addButton = document.getElementById("add-service-row");
    if (addButton) addButton.addEventListener("click", () => {
      const row = document.createElement("div");
      row.className = "service-fee-row";
      row.innerHTML = `
        <label>Service name<input type="text" name="service_name[]" list="service-catalog-options" placeholder="Choose or type a service" required></label>
        <label>Fee<input class="service-fee-input" type="number" min="0" step="0.01" name="service_amount[]" value="0.00" required></label>
        <label class="service-scope-field">Scope of services<textarea name="service_scope[]" rows="3" placeholder="Describe the work included" required></textarea></label>
        <button class="btn remove-service-row" type="button" aria-label="Remove service">Remove</button>`;
      feeList.appendChild(row);
      bindServiceRow(row);
      row.querySelector('input[name="service_name[]"]').focus();
      updateServiceTotals();
    });
    if (currencySelect) currencySelect.addEventListener("change", updateServiceTotals);
    updateServiceTotals();
  }

  const catalogNameInput = document.querySelector('form.catalog-form input[name="name"]');
  const catalogScopeInput = document.querySelector('form.catalog-form textarea[name="scope"]');
  bindAutomaticScope(catalogNameInput, catalogScopeInput);

  const serviceSelect = document.getElementById("individual-service-select");
  if (serviceSelect) {
    const currency = serviceSelect.dataset.currency || "INR";
    const currencySymbol = currencySymbols[currency] || currency + " ";
    const formatSelected = value => currencySymbol + Number(value || 0).toLocaleString("en-IN", {
      minimumFractionDigits: 2, maximumFractionDigits: 2
    });
    function updateSelectedService() {
      const option = serviceSelect.options[serviceSelect.selectedIndex];
      const fee = Number(option ? option.dataset.fee : 0);
      const igst = fee * 0.18;
      document.getElementById("individual-fee").textContent = formatSelected(fee);
      document.getElementById("individual-igst").textContent = formatSelected(igst);
      document.getElementById("individual-total").textContent = formatSelected(fee + igst);
    }
    serviceSelect.addEventListener("change", updateSelectedService);
    updateSelectedService();
  }
});
