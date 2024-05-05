# Save Image Extended for ComfyUI

<p align="center">
 <img src="assets/example.png" />
</p>

 Customize the information saved in file- and folder names. Use the values of sampler parameters as part of file or folder names. <br>Save data about the generated job (sampler, prompts, models) as entries in a `json` (text) file, in each folder.

 ## Installation
1. Open a terminal inside the 'custom_nodes' folder located in your ComfyUI installation dir
2. Use the `git clone` command to clone the [save-image-extended-comfyui](https://github.com/audioscavenger/ComfyUI-PowerSave) repo.
```
git clone https://github.com/audioscavenger/ComfyUI-PowerSave
```

## Parameters / Usage

- `output_ext` -  File extension: PNG by default, or WEBP.
- `filename_prefix` -  String prefix added to files.
- `filename_keys` - Comma separated string with sampler parameters to add to filename. E.g: `sampler_name, scheduler, cfg, denoise` Added to filename in written order. `resolution`  also works. `vae_name` `model_name` (upscale model), `ckpt_name` (checkpoint) are others that should work. Here you can try any parameter name of any node. As long as the parameter has the same variable name defined in the `prompt` object they should work. The same applies to `foldername_keys`. 
- `foldername_prefix` - String prefix added to folders.
- `foldername_keys` - Comma separated string with sampler parameters to add to foldername.
- `delimiter` - Delimiter character, either `underscore`, `dot`, or `comma`.
- `save_job_data` - If enabled, saves information about each job as entries in a `jobs.json` text file, inside the generated folder. Mulitple options for saving `prompt`, `basic data`, `sampler settings`, `loaded models`.
- `job_data_per_image` - When enabled, saves individual job data files for each image.
- `job_custom_text` - Custom string to save along with the job data. Right click the node and convert to input to connect with another node.
- `save_metadata` - Saves metadata into the image.
- `counter_digits` - Number of digits used for the image counter. `3` = image_001.png. Will adjust the counter if files are deleted. Looks for the highest number in the folder, does not fill gaps.
- `counter_position` - Image counter first or last in the filename.
- `one_counter_per_folder` - Toggles the counter. Either one counter per folder, or resets when a parameter/prompt changes.
- `image_preview` - Turns the image preview on and off.

## Node inputs

- `images` - The generated images.
- `positive_text_opt` - Optional string input for when using custom nodes for positive prompt text.
- `negative_text_opt` - Optional string input for when using custom nodes for negative prompt text.

## Automatic folder names and date/time in names

Convert the 'prefix' parameters to inputs (right click in the node and select e.g 'convert foldername_prefix to input'. Then attach the 'Get Date Time String' custom node from JPS to these inputs. This way a new folder name can be automatically generated each time generate is pressed.
#
Disclaimer: Does not check for illegal characters entered in file or folder names. May not be compatible with every other custom node, depending on changes in the `prompt` object. Tested and working with default samplers, Efficiency nodes and UltimateSDUpscale.
#
<br>

<p align="center">
 <img src="assets/prompts.png" />
<br><br>
 Happy saving!
</p>



