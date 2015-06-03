Ext.define('MyApp.model.service.OrganizationServiceModel', {
    extend: 'Ext.data.Model',
    fields: [
        {name: 'id', type: 'int'},
        {name: 'first_name', type: 'string'},
        {name: 'last_name', type: 'string'},
        {name: 'middle_name', type: 'string'},
        {name: 'birthdate', type: 'date', dateReadFormat: 'Y-m-d'},
        {name: 'gender', type: 'string'},
        {name: 'policy', type: 'string'},
        {name: 'start_date', type: 'date', dateReadFormat: 'Y-m-d'},
		{name: 'end_date', type: 'date', dateReadFormat: 'Y-m-d'},
        {name: 'division_code', type: 'string'},
        {name: 'service_code', type: 'string'},    
        {name: 'quantity', type: 'int'},
        {name: 'disease_code', type: 'string'},
		{name: 'tariff', type: 'float'},
        {name: 'accepted', type: 'float'},
        {name: 'worker_code', type: 'string'},
        {name: 'anamnesis', type: 'string'},
		{name: 'uet', type: 'float'},
        {name: 'event_id', type: 'int'},
        {name: 'errors', type: 'string'},
		{name: 'service_comment', type: 'string'},
		{name: 'event_comment', type: 'string'},
		{name: 'profile_code', type: 'int'},
		{name: 'profile_name', type: 'string'},
		{name: 'division_name', type: 'string'},
		{name: 'service_name', type: 'string'},
		{name: 'disease_name', type: 'string'},
		{name: 'initial_disease', type: 'string'},
		{name: 'basic_disease', type: 'string'},
		{name: 'complicated_disease', type: 'string'},
		{name: 'concomitant_disease', type: 'string'},
		{name: 'payment_code', type: 'int'},
		{name: 'term', type: 'string'},
		{name: 'result', type: 'string'},
		{name: 'department', type: 'string'},
		{name: 'i', type: 'int'}
    ]                    
})