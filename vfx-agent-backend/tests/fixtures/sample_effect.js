class Effect {
  static CONTRACT_VERSION = 2;

  static CONFIG = {
    circle_size: {
      default: 30,
      type: 'range',
      min: 5,
      max: 100,
      step: 1,
      label: 'Circle size',
      description: 'Higher values make the circle larger',
    },
    circle_color: {
      default: '#ff0000',
      type: 'color',
      label: 'Circle color',
      description: 'Changes the circle fill color',
    },
  };

  constructor() {}

  display(sketch, frameData, params) {
    sketch.push();
    sketch.fill(params.circle_color);
    sketch.noStroke();
    sketch.ellipse(100, 100, params.circle_size, params.circle_size);
    sketch.pop();
  }
}
