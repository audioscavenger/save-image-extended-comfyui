import { app } from "../../../scripts/app.js";

// Adds context menu entries, code partly from pyssssscustom-scripts

function addMenuHandler(nodeType, cb) {
	const getOpts = nodeType.prototype.getExtraMenuOptions;
	nodeType.prototype.getExtraMenuOptions = function () {
		const r = getOpts.apply(this, arguments);
		cb.apply(this, arguments);
		return r;
	};
}

function addNode(name, nextTo, options) {
	console.log("name:", name);
	console.log("nextTo:", nextTo);
	options = { side: "left", select: true, shiftY: 0, shiftX: 0, ...(options || {}) };
	const node = LiteGraph.createNode(name);
	app.graph.add(node);
	
	node.pos = [
		options.side === "left" ? nextTo.pos[0] - (node.size[0] + options.offset): nextTo.pos[0] + nextTo.size[0] + options.offset,
		
		nextTo.pos[1] + options.shiftY,
	];
	if (options.select) {
		app.canvas.selectNode(node, false);
	}
	return node;
}

app.registerExtension({
	name: "SIEContextmenu",
  async setup(app) {
    app.ui.settings.addSetting({
      id: "SIE.helpPopup",
      name: "🦛 SIE: Help popups",
      defaultValue: true,
      type: "boolean",
      options: (value) => [
        { value: true, text: "On", selected: value === true },
        { value: false, text: "Off", selected: value === false },
      ],
    });
  }
});
