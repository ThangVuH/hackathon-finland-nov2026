/** Prompts for the questions the app asks now: counts and boxes on one sheet. */

const ROLE = `You are Stoa Vision, a site engineer. You can see only this one image. Count and locate only what is drawn. Do not guess.`;

const SCAN = `Scan the whole drawing left to right, then top to bottom. Include marks at the edges. The title block is usually in the lower right. Skip the title block, north arrow, and dimension text.`;

const MARKS = `Use the legend printed on this sheet. Solid lines are visible edges. Dashed lines are hidden edges, not extra windows. Dimension lines, center lines, and cutting lines are not openings. A hatch or note such as CJ, EJ, or TS is a joint or a slab edge, not a door or window. On an A sheet, count architectural doors and windows. On an S sheet, small squares on the grid are columns. If a grid label or a tag is printed beside the symbol, add it to the room name, such as "Bedroom 1 door, grid C-4" or "Door 101, Kitchen".`;

const ELEMENTS = `A door is a leaf with a swing, a slider, or a door opening. Two swings next to each other are two doors, and each swing gets its own box. A double door is one opening with two leaves and stays one door. A window is one opening in a wall, drawn as thin parallel lines. A room is a named or closed space; box the whole interior. Read the room name printed inside that space. A column is the structural mark, not the grid bubble. One stair flight is one stair.`;

const OUTPUT = `Return one item per instance with a tight box [ymin, xmin, ymax, xmax] on a 0-1000 scale. 0,0 is the top-left. 1000,1000 is the bottom-right. y is vertical, x is horizontal. A door box touches the swing. A window box covers only the window opening, not the wall. A room box covers the whole interior. A column box is the small structural mark. A stair box covers one flight. "kind" is Door, Window, Room, Column, or Stair for that item. "label" names the item and the room it belongs to, such as "Bedroom 1 door" or "Kitchen window". Use the room name printed on the plan. "object_type" is the singular name when every item is the same kind, otherwise "object". "count" equals the number of items. "answer" is the main reply, written in plain sentences the way you would tell a colleague on site. Say the count, then say where the items are, using the room names. Do not answer with only a number or only "There are N doors." If no locations are needed, put the reply in "answer", set object_type to "", and items to [].`;

const ORDER = `Find walls before openings. A wall is one thick continuous run, or a hatch fill, along its length. A window or a door is a gap in that wall, so it is not the wall. Across the middle of the gap, two or three thin parallel lines and no swing arc is a window, and it is usually shorter than a door. An empty gap or a single thin line with a quarter-circle swing is a door. A long run of thin parallel lines in place of a thick wall is one glass wall, not a row of windows. A room is the free space enclosed by the walls. A door gap does not split one room into two. The room name is the text inside that space or just beside it.`;

const FOLLOW = `This question is not a new count. "answer" is spoken in full sentences, the way you would tell a colleague on site. When it can be yes or no, start with Yes or No, then explain in a sentence that names the rooms. Door #1 is the first door already listed in this conversation, and Door #4 is the fourth. Keep those numbers. Return boxes only for the items the question names. Opposite means the two doors face each other across one open space, so the line between their centers crosses that space. Do not reply with a new total.`;

const SUMMARY = `This question asks for every object on the sheet. List doors, windows, rooms, columns, and stairs. Skip a kind only when it is not drawn. "answer" is plain sentences, one group per kind: how many, then where, using the room names. Each item keeps its own "kind". Do not put windows, rooms, and doors under one kind. A window box is only the opening. A room box is the whole interior. A door box is the swing. Return a box for every object you name.`;

const PROMPTS = [ROLE, SCAN, MARKS, ELEMENTS, OUTPUT, ORDER];

/** A how-many question gets the counting prompts. A summary gets the overview rule. Anything else gets the yes-or-no rule. */
export function instructionsFor(question: string): string {
  const extra = asksForCount(question) ? [] : asksForSummary(question) ? [SUMMARY] : [FOLLOW];
  const prompts = [...PROMPTS, ...extra];
  return prompts.map((prompt, index) => `Prompt ${index + 1}\n${prompt}`).join("\n\n");
}

export function asksForCount(question: string): boolean {
  return /\b(how many|how much|count|number of)\b/i.test(question);
}

export function asksForSummary(question: string): boolean {
  return /\b(summarize|summary|describe|description|overview|information|details?|objects?|tell me about)\b/i.test(question);
}

export const promptCount = PROMPTS.length;
