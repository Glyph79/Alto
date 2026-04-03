let svg, width, height, g;
let nodes = [], links = [];

async function loadNetwork() {
    try {
        const response = await fetch('/api/network');
        if (!response.ok) throw new Error('Failed to load network data');
        const data = await response.json();
        nodes = data.nodes;
        links = data.links;
        renderTreeLayout();
    } catch (err) {
        console.error(err);
        document.getElementById('graph-container').innerHTML = `<div style="color:#ff6b9d; text-align:center; padding:40px;">Error loading network: ${err.message}</div>`;
    }
}

function renderTreeLayout() {
    const container = document.getElementById('graph-container');
    container.innerHTML = '';
    width = container.clientWidth;
    height = container.clientHeight;

    svg = d3.select('#graph-container')
        .append('svg')
        .attr('width', width)
        .attr('height', height)
        .call(d3.zoom().on('zoom', (event) => {
            g.attr('transform', event.transform);
        }))
        .append('g');

    g = svg;

    // Build a hierarchy from the graph
    const nodeMap = new Map();
    nodes.forEach(n => {
        nodeMap.set(n.id, { ...n, children: [] });
    });

    links.forEach(link => {
        const parent = nodeMap.get(link.source);
        const child = nodeMap.get(link.target);
        if (parent && child) {
            parent.children.push(child);
        }
    });

    // Find root nodes (nodes with no parent)
    const hasParent = new Set();
    links.forEach(link => hasParent.add(link.target));
    const rootNodes = nodes.filter(n => !hasParent.has(n.id)).map(n => nodeMap.get(n.id));

    // Create a dummy root to hold multiple trees
    const dummyRoot = { children: rootNodes };

    // Use d3.tree with left-to-right orientation (swap x/y)
    // nodeSize: [verticalSpacing, horizontalSpacing]
    const treeLayout = d3.tree()
        .nodeSize([60, 120])  // tighter: 60px vertical, 120px horizontal
        .separation((a, b) => (a.parent === b.parent ? 1 : 1.2));

    const root = d3.hierarchy(dummyRoot);
    const treeData = treeLayout(root);

    // Swap x and y for left-to-right (x = depth, y = vertical position)
    const nodesLayout = treeData.descendants().slice(1); // exclude dummy root
    nodesLayout.forEach(node => {
        const origX = node.x;
        const origY = node.y;
        node.x = origY;  // horizontal
        node.y = origX;  // vertical
    });

    // Map back to our nodes
    const positionedNodes = [];
    nodesLayout.forEach(layoutNode => {
        const originalNode = layoutNode.data;
        if (originalNode.id) {
            positionedNodes.push({
                ...originalNode,
                x: layoutNode.x,
                y: layoutNode.y
            });
        }
    });

    const posMap = new Map();
    positionedNodes.forEach(n => posMap.set(n.id, n));

    // Draw straight lines (neural network style)
    g.append('g')
        .attr('class', 'links')
        .selectAll('line')
        .data(links)
        .enter().append('line')
        .attr('x1', d => posMap.get(d.source)?.x ?? 0)
        .attr('y1', d => posMap.get(d.source)?.y ?? 0)
        .attr('x2', d => posMap.get(d.target)?.x ?? 0)
        .attr('y2', d => posMap.get(d.target)?.y ?? 0)
        .attr('stroke', '#8888ff')
        .attr('stroke-width', 1.5)
        .attr('stroke-opacity', 0.6);

    // Draw nodes
    const nodeGroup = g.append('g')
        .attr('class', 'nodes')
        .selectAll('g')
        .data(positionedNodes)
        .enter().append('g')
        .attr('class', 'node')
        .attr('transform', d => `translate(${d.x},${d.y})`);

    nodeGroup.append('circle')
        .attr('r', d => d.type === 'group' ? 14 : (d.type === 'root' ? 10 : 8))
        .attr('fill', d => {
            if (d.type === 'group') return '#6c63ff';
            if (d.type === 'root') return '#ffaa66';
            return '#00ff88';
        })
        .attr('stroke', '#fff')
        .attr('stroke-width', 1.5);

    // Tooltips
    nodeGroup.on('mouseenter', function(event, d) {
        const tooltip = d3.select('body').append('div')
            .attr('class', 'tooltip')
            .html(`<strong>${d.name}</strong><br>Type: ${d.type}${d.topic ? '<br>Topic: '+d.topic : ''}${d.section ? '<br>Section: '+d.section : ''}`)
            .style('left', (event.pageX + 10) + 'px')
            .style('top', (event.pageY - 28) + 'px');
        d3.select(this).select('circle').attr('stroke-width', 2.5);
    }).on('mouseleave', function() {
        d3.selectAll('.tooltip').remove();
        d3.select(this).select('circle').attr('stroke-width', 1.5);
    });

    // Auto-fit to view
    const minX = d3.min(positionedNodes, d => d.x);
    const maxX = d3.max(positionedNodes, d => d.x);
    const minY = d3.min(positionedNodes, d => d.y);
    const maxY = d3.max(positionedNodes, d => d.y);
    const padding = 50;
    const fitScale = Math.min(width / (maxX - minX + padding), height / (maxY - minY + padding));
    const fitX = (width - (maxX + minX) * fitScale) / 2;
    const fitY = (height - (maxY + minY) * fitScale) / 2;
    g.attr('transform', `translate(${fitX},${fitY}) scale(${fitScale})`);
}

window.addEventListener('resize', () => {
    if (svg) {
        const newWidth = document.getElementById('graph-container').clientWidth;
        const newHeight = document.getElementById('graph-container').clientHeight;
        svg.attr('width', newWidth).attr('height', newHeight);
        renderTreeLayout();
    }
});

document.getElementById('reset-btn').addEventListener('click', () => {
    renderTreeLayout();
});

loadNetwork();