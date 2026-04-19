let svg, width, height, g, zoom;
let nodes = [], links = [];
let activeTooltip = null;
let activeTooltipNode = null;

// Helper to show a card when no model or no groups
function showNoModelCard(message) {
    const container = document.getElementById('graph-container');
    // Remove any existing card or svg
    container.innerHTML = '';
    const card = document.createElement('div');
    card.className = 'no-model-card';
    card.innerHTML = `
        <div class="card-header">
            <span class="card-icon">📁</span>
            <h3>No Model Loaded</h3>
        </div>
        <div class="card-content">
            <p>${message}</p>
            <p class="card-hint">Use the <strong>Alto Trainer</strong> to create or import a model.</p>
        </div>
    `;
    container.appendChild(card);
}

function hideCard() {
    const container = document.getElementById('graph-container');
    const existingCard = container.querySelector('.no-model-card');
    if (existingCard) existingCard.remove();
}

async function loadNetwork() {
    try {
        const response = await fetch('/api/network');
        if (!response.ok) throw new Error('Failed to load network data');
        const data = await response.json();
        
        if (data.message) {
            showNoModelCard(data.message);
            return;
        }
        
        nodes = data.nodes;
        links = data.links;
        
        if (nodes.length === 0) {
            showNoModelCard('The current model has no groups or follow‑up trees.');
            return;
        }
        
        hideCard();
        renderTreeLayout();
    } catch (err) {
        console.error(err);
        showNoModelCard(`Error loading network: ${err.message}`);
    }
}

function updateTooltipPosition() {
    if (!activeTooltip || !activeTooltipNode) return;
    const nodeElement = activeTooltipNode.node();
    if (!nodeElement) return;
    const rect = nodeElement.getBoundingClientRect();
    activeTooltip
        .style('left', (rect.left + rect.width / 2 + 10) + 'px')
        .style('top', (rect.top - 28) + 'px');
}

function hideTooltip() {
    if (activeTooltip) {
        activeTooltip.remove();
        activeTooltip = null;
        activeTooltipNode = null;
    }
}

function renderTreeLayout() {
    const container = document.getElementById('graph-container');
    container.innerHTML = '';
    width = container.clientWidth;
    height = container.clientHeight;

    zoom = d3.zoom().on('zoom', (event) => {
        g.attr('transform', event.transform);
        updateTooltipPosition();
    });

    svg = d3.select('#graph-container')
        .append('svg')
        .attr('width', width)
        .attr('height', height)
        .call(zoom);

    svg.on('mousedown', (event) => {
        if (event.button === 1) {
            event.preventDefault();
            return false;
        }
        hideTooltip();
    }).on('contextmenu', (event) => {
        event.preventDefault();
    });

    g = svg.append('g');

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

    const hasParent = new Set();
    links.forEach(link => hasParent.add(link.target));
    const rootNodes = nodes.filter(n => !hasParent.has(n.id)).map(n => nodeMap.get(n.id));

    const dummyRoot = { children: rootNodes };

    const treeLayout = d3.tree()
        .nodeSize([60, 80])
        .separation((a, b) => (a.parent === b.parent ? 1 : 1.1));

    const root = d3.hierarchy(dummyRoot);
    const treeData = treeLayout(root);

    const nodesLayout = treeData.descendants().slice(1);
    nodesLayout.forEach(node => {
        const origX = node.x;
        const origY = node.y;
        node.x = origY;
        node.y = origX;
    });

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

    g.append('g')
        .attr('class', 'links')
        .selectAll('line')
        .data(links)
        .enter().append('line')
        .attr('class', 'link')
        .attr('x1', d => posMap.get(d.source)?.x ?? 0)
        .attr('y1', d => posMap.get(d.source)?.y ?? 0)
        .attr('x2', d => posMap.get(d.target)?.x ?? 0)
        .attr('y2', d => posMap.get(d.target)?.y ?? 0);

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

    nodeGroup.on('mouseenter', function(event, d) {
        hideTooltip();
        activeTooltipNode = d3.select(this);
        activeTooltip = d3.select('body').append('div')
            .attr('class', 'tooltip')
            .html(`<strong>${d.name}</strong><br>Type: ${d.type}${d.topic ? '<br>Topic: '+d.topic : ''}${d.section ? '<br>Section: '+d.section : ''}`);
        updateTooltipPosition();
        d3.select(this).select('circle').attr('stroke-width', 2.5);
    }).on('mouseleave', function() {
        hideTooltip();
        d3.select(this).select('circle').attr('stroke-width', 1.5);
    });

    const minX = d3.min(positionedNodes, d => d.x);
    const maxX = d3.max(positionedNodes, d => d.x);
    const minY = d3.min(positionedNodes, d => d.y);
    const maxY = d3.max(positionedNodes, d => d.y);
    const defaultScale = 0.8;
    const centerX = (minX + maxX) / 2;
    const centerY = (minY + maxY) / 2;
    const translateX = width / 2 - centerX * defaultScale;
    const translateY = height / 2 - centerY * defaultScale;

    const initialTransform = d3.zoomIdentity
        .translate(translateX, translateY)
        .scale(defaultScale);
    
    svg.call(zoom.transform, initialTransform);
}

function resetZoom() {
    if (!svg || !zoom) return;
    hideTooltip();
    renderTreeLayout();
}

window.addEventListener('resize', () => {
    if (svg) {
        svg.attr('width', document.getElementById('graph-container').clientWidth)
           .attr('height', document.getElementById('graph-container').clientHeight);
        hideTooltip();
        renderTreeLayout();
    }
});

document.getElementById('reset-btn').addEventListener('click', () => {
    resetZoom();
});

loadNetwork();