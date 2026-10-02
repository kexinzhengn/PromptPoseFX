class Effect {
  static CONTRACT_VERSION = 2;

  static CONFIG = {
    trail_length: {
      default: 20,
      type: 'range',
      min: 2,
      max: 120,
      step: 1,
      label: 'Trail Length',
      description: 'Higher values extend the trail farther',
    },
  };

  constructor() {}

  display(sketch, frameData, params) {
    const history = frameData.getJointHistory('left_wrist', params.trail_length);
    sketch.push();
    for (let index = 1; index < history.length; index++) {
      const previous = history[index - 1];
      const point = history[index];
      if (!previous.valid || !point.valid || !point.connected) continue;
      sketch.line(previous.x, previous.y, point.x, point.y);
    }
    sketch.pop();
  }
}
