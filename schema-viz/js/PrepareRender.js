//return an array based on user selection 
    var schema = 'NF';
    var tangled_tree_data = parseJSON('files/nf-tools-db.json');
    tangled_tree_data.then(tangled_tree_dta => {
        //get tangle tree layout
        var chart_dta = chart(tangled_tree_dta);

        //draw collapsible tree
        createCollapsibleTree(chart_dta, schema);
    });