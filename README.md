# Save Image Extended for ComfyUI

<p align="center">
 <img src="assets/save-image-extended-comfyui-example.png" />
</p>

* Customize the folder, sub-folders, and filenames of your images! 
* Save data about the generated job (sampler, prompts, models) as entries in a `json` (text) file, in each folder.
* Use the values of ANY node's widget, by simply adding its badge number in the form _id.widget_name_: 

<br>
<p align="center">
 <img src="assets/save-image-extended-comfyui-named_nodes_widgets-example.png" />
<br><br>
 Happy saving!
</p>

*Reboot by AudioscavengeR since 2024-05-05*

 ## Installation
1. Open a terminal inside the 'custom_nodes' folder located in your ComfyUI installation dir
2. Use the `git clone` command to clone the [save-image-extended-comfyui](https://github.com/audioscavenger/save-image-extended-comfyui) repo.
```
git clone https://github.com/audioscavenger/save-image-extended-comfyui
```

## Parameters / Usage
| Attribute | Description |
| --- | --- |
| `filename_prefix` |  String prefix added to files. |
| `filename_keys` | Comma separated string with sampler parameters to add to filename. E.g: `sampler_name, scheduler, cfg, denoise` Added to filename in written order. `resolution`  also works. `vae_name` `model_name` (upscale model), `ckpt_name` (checkpoint) are others that should work. Here you can try any parameter name of any node. As long as the parameter has the same variable name defined in the `prompt` object they should work. The same applies to `foldername_keys`. |
| `foldername_prefix` | String prefix added to folders. |
| `foldername_keys` | Comma separated string with _sampler_ parameters to add to foldername. Add more subfolders by prepending "./" to the key name. |
| `delimiter` | **now a free field** Delimiter = 1 character, can be anything your file system supports. Windows users should still use "/" for subfolders. |
| `save_job_data` | If enabled, saves information about each job as entries in a `jobs.json` text file, inside the generated folder. Mulitple options for saving `prompt`, `basic data`, `sampler settings`, `loaded models`. |
| `job_data_per_image` | When enabled, saves individual job data files for each image. |
| `job_custom_text` | Custom string to save along with the job data. Right click the node and convert to input to connect with another node. |
| `save_metadata` | Saves metadata into the image. |
| `counter_digits` | Number of digits used for the image counter. `3` = image_001.png. Will adjust the counter if files are deleted. Looks for the highest number in the folder, does not fill gaps. |
| `counter_position` | Image counter first or last in the filename. |
| `one_counter_per_folder` | Toggles the counter. Either one counter per folder, or resets when a parameter/prompt changes. |
| `image_preview` | Turns the image preview on and off. |
| `output_ext` |  File extension: PNG by default, or WEBP (coming soon). |

Unknown key names in `filename_keys` and `foldername_keys` are treated as custom strings.

## Node inputs

- `images` - The generated images.

Optional:
- `positive_text_opt` - Optional string input for when using custom nodes for positive prompt text.
- `negative_text_opt` - Optional string input for when using custom nodes for negative prompt text.

## Automatic folder names and date/time in names

Convert the 'prefix' parameters to inputs (right click in the node and select e.g 'convert foldername_prefix to input'. Then attach the 'Get Date Time String' custom node from JPS to these inputs. This way a new folder name can be automatically generated each time generate is pressed.
#
Disclaimer: Does not check for illegal characters entered in file or folder names. May not be compatible with every other custom node, depending on changes in the `prompt` object. 
Tested and working with default samplers, Efficiency nodes, UltimateSDUpscale, ComfyRoll, composer, NegiTools, and 45 other nodes.
#
Imcompatible with *extended-saveimage-comfyui* - This node can be discarded, as it only offers WebP output. I will add WebP and Avif very soon.
#
<br>
<p align="center">
 <img src="assets/save-image-extended-comfyui-jobs-example.png" />
<br><br>
 Happy saving!
</p>

#
You asked for it... Now you can select which node to get the widget values from! Formerly, this custom node would simply return the last value found: useles if you have many Ksamplers...
Make sure you enable the badge IDs to benefit from this:
<br>
<p align="center">
 <img src="assets/ComfyUI-enable-badge-ids.png" />
<br><br>
 Happy saving!
</p>


## RoadMap

I won't promise anything, just like @thedyze did not promise anything when they released this custom node. Then disappeared for good 3 months later. That's fine, I do that too. 

However, I do provide a way to contact me, and will accept PR and collabs. Once I feel like I don't have time to work on it, I will gladly transfer ownership or let collabs maintain it.

- [x] now accepts inexistant keys and use them as fixed strings
- [x] now accepts inexistant keys with / and use them as subfolders
- [x] delimiter is now whatever you want, free field. Limited to 16 characters tho
- [x] all is instance methods, previously we had @staticmethods. Why? Don't know.
- [x] check get_latest_counter: does it still work with subfolders? yessir
- [x] bugfix: custom_name was not updated for int and floats
- [x] for each keys, we return only the last value found in the prompt. Not the last Ksampler. Impossible to know which one is the last. Therefore, simply use this syntax: number.widget_name
- [x] filename_keys and foldername_keys become too large, switch to multiline
- [x] also removes subfolders from values found, when people use subfolders like SD15/pytorch_blah.pt etc
- [x] added what I was looking for the last 6 months in the first place: 123.attribute from nodes!
- [x] limit delimiter to 1 char, or file counter will get too complex
- [ ] save_job_to_json is pretty much useless actually, since it only saves the last value found for each node
- [ ] bugfix: when using /name in foldername_keys, Comfy thinks you want to save outside the output folder
- [ ] what is job_custom_text?
- [ ] what is jobs.json? History, alraight. What do you do with that? Can we disable it?
- [ ] improve get_latest_counter: fails when user renames files: appends text after counter
- [ ] integrate pngquant
- [ ] integrate optipng
- [ ] integrate avif? can it hold metadata?
- [ ] integrate webp


