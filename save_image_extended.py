import os
import re
import sys
import json
import numpy as np
import locale
from datetime import datetime
from pathlib import Path
import folder_paths
import pprint
import piexif
import piexif.helper

version = 2.6.5

avif_supported = False
jxl_supported = False

# Avif is included in requirements.txt
try:
  import pillow_avif
except:
  print(f"\033[92m[save_image_extended]\033[0m AVIF is not supported. To add it: pip install pillow pillow-avif-plugin\033[0m") 
  pass
else:
  print(f"\033[92m[save_image_extended] AVIF is supported! Woohoo!\033[0m") 
  avif_supported = True

# Jxl requires jxlpy wheel to be compiled, and a valid MSVC environment, which is complex task
try:
  from jxlpy import JXLImagePlugin
except:
  print(f"\033[92m[save_image_extended]\033[0m JXL is not supported. To add it: pip install jxlpy\033[0m") 
  print(f"\033[92m[save_image_extended]\033[0m                       You will need a valid MSVC env to build the wheel\033[0m") 
  pass
else:
  jxl_supported = True

# PIL must be loaded after pillow_avif
from PIL import Image, ExifTags
from PIL.PngImagePlugin import PngInfo

sys.path.insert(0, os.path.join(os.path.dirname(os.path.realpath(__file__)), 'comfy'))
original_locale = locale.setlocale(locale.LC_TIME, '')


# class SaveImageExtended -------------------------------------------------------------------------------
class SaveImageExtended:
  RETURN_TYPES = ()
  FUNCTION = 'save_images'
  OUTPUT_NODE = True
  CATEGORY = 'image'
  DESCRIPTION = """
### subfolders:
- you can use / or ./ or even ../ to start from parent
- you can also use / as the separator
- if your widget name has subfolders like SDXL/whatnot, you will have subfolders too
### Sample datetime formats: see [man datetime](https://www.man7.org/linux/man-pages/man1/date.1.html)
- %F = %Y-%m-%d = 2024-05-22
- %H-%M-%S = 09-13-58
- %D = 05/22/24 (subfolders)

"""

  type                    = 'output'
  
  png_compress_level      = 9
  avif_quality            = 60
  webp_quality            = 75
  jpeg_quality            = 91
  jxl_quality             = 91
  # tiff_quality has no impact unless you start meddling with the compressions algorithms
  tiff_quality            = 91
  # optimize_image only works for jpeg, with like just 2% reduction in size
  optimize_image          = True
  
  filename_prefix         = 'ComfyUI'
  filename_keys           = 'sampler_name, cfg, steps, %F %H-%M-%S'
  foldername_prefix       = ''
  foldername_keys         = 'ckpt_name'
  delimiter               = '-'
  save_job_data           = 'disabled'
  job_data_per_image      = False
  job_custom_text         = ''
  save_metadata           = True
  counter_digits          = 4
  counter_position        = 'last'
  counter_positions       = ['last', 'first']
  one_counter_per_folder  = True
  image_preview           = True
  extToRemove             = ['.safetensors', '.ckpt', '.pt', '.bin', '.pth']
  output_ext              = '.webp'
  output_exts             = ['.webp', '.png', '.jpg', '.jpeg', '.gif', '.tiff', '.bmp']
  quality                 = 75

  print(f"\033[92m[save_image_extended]\033[0m version: {version}\033[0m")
  if jxl_supported:
    output_exts.insert(0, '.jxl')
  # if pillow_avif not in sys.modules:
  if avif_supported:
    output_exts.insert(0, '.avif')

  def __init__(self):
    self.output_dir = folder_paths.get_output_directory()
    self.prefix_append = ''
    
  
  """
  Return a dictionary which contains config for all input fields.
  Some types (string): "MODEL", "VAE", "CLIP", "CONDITIONING", "LATENT", "IMAGE", "INT", "STRING", "FLOAT".
  Input types "INT", "STRING" or "FLOAT" are special values for fields on the node.
  The type can be a list for selection.
  
  Returns: `dict`:
      - Key input_fields_group (`string`): Can be either required, hidden or optional. A node class must have property `required`
      - Value input_fields (`dict`): Contains input fields config:
          * Key field_name (`string`): Name of a entry-point method's argument
          * Value field_config (`tuple`):
              + First value is a string indicate the type of field or a list for selection.
              + Secound value is a config for type "INT", "STRING" or "FLOAT".
  """
  @classmethod
  def INPUT_TYPES(self):
    return {
      'required': {
        'images': ('IMAGE', ),
        'filename_prefix': ('STRING', {'default': self.filename_prefix, 'multiline': False}),
        'filename_keys': ('STRING', {'default': self.filename_keys, 'multiline': True}),
        'foldername_prefix': ('STRING', {'default': self.foldername_prefix, 'multiline': False}),
        'foldername_keys': ('STRING', {'default': self.foldername_keys, 'multiline': True}),
        'delimiter': ('STRING', {'default': self.delimiter, 'multiline': False}),
        'save_job_data': ([
          'disabled', 
          'prompt', 
          'basic, prompt', 
          'basic, sampler, prompt', 
          'basic, models, sampler, prompt'
        ], {'default': self.save_job_data}),
        'job_data_per_image': ('BOOLEAN', {"default": self.job_data_per_image}),
        'job_custom_text': ('STRING', {'default': self.job_custom_text, 'multiline': False}),
        'save_metadata': ('BOOLEAN', {'default': self.save_metadata}),
        'counter_digits': ('INT', {
          "default": self.counter_digits, 
          "min": 1, 
          "max": 8, 
          "step": 1,
          "display": "silder"
         }),
        'counter_position': (self.counter_positions, {'default': self.counter_position}),
        'one_counter_per_folder': ('BOOLEAN', {'default': self.one_counter_per_folder}),
        'image_preview': ('BOOLEAN', {'default': self.image_preview}),
        'output_ext': (self.output_exts, {'default': self.output_ext}),
        'quality': ('INT', {
          "default": self.quality, 
          "min": 1, 
          "max": 100, 
          "step": 1,
          "display": "silder"
         }),
      },
      'optional': {
        'positive_text_opt': ('STRING', {'forceInput': True}),
        'negative_text_opt': ('STRING', {'forceInput': True}),
                    },
      'hidden': {'prompt': 'PROMPT', 'extra_pnginfo': 'EXTRA_PNGINFO'},
    }
  
  
  def get_subfolder_path(self, image_path, output_path):
    image_path = Path(image_path).resolve()
    output_path = Path(output_path).resolve()
    relative_path = image_path.relative_to(output_path)
    subfolder_path = relative_path.parent
    
    return str(subfolder_path)
  
  
  # Get current counter number from file names
  def get_latest_counter(self, one_counter_per_folder, folder_path, filename_prefix, counter_digits=counter_digits, counter_position=counter_position, output_ext=output_ext):
    counter = 1
    if not os.path.exists(folder_path):
      print(f"SaveImageExtended {version} error: Folder {folder_path} does not exist, starting counter at 1.")
      return counter
    
    try:
      files = [file for file in os.listdir(folder_path) if file.endswith(output_ext)]
      extLen = len(output_ext)
      if files:
        if counter_position not in self.counter_positions: counter_position = self.counter_position
        if counter_position == 'last':
          # BUG: this works only if extension is 3 letters like png, this will break with webp and avif:
          counters = [int(file[-(extLen + counter_digits):-extLen]) if file[-(extLen + counter_digits):-extLen].isdecimal() else 0 for file in files if one_counter_per_folder or file.startswith(filename_prefix)]
        else:
          counters = [int(file[:counter_digits]) if file[:counter_digits].isdecimal() else 0 for file in files if one_counter_per_folder or file[counter_digits +1:].startswith(filename_prefix)]
        
        if counters:
          counter = max(counters) + 1
    
    except Exception as e:
      print(f"SaveImageExtended {version} error: An error occurred while finding the latest counter: {e}")
    
    return counter
  
  
  # find_keys_recursively is a self-updating recursive method, that will update the dict found_values
  def find_keys_recursively(self, prompt={}, keys_to_find=[], found_values={}):
    for key, value in prompt.items():
      if key in keys_to_find:
        found_values[key] = value
      elif isinstance(value, dict):
        self.find_keys_recursively(value, keys_to_find, found_values)
  
  
  def cleanup_fileName(self, file='', extToRemove=extToRemove):
    if isinstance(file, str):
      # takes care of all the possible safetensor extensions under the sun
      # cannot do that... maybe the user want a string.string fixed value to use, that does not end with extToRemove
      # file = os.path.splitext(os.path.basename(file))[0]
      for ext in extToRemove: file = file.removesuffix(ext)
    return file
  
  
  # this method pretty much does the same as find_keys_recursively, except it's for job.json export
  def find_parameter_values(self, target_keys, prompt={}, found_values={}):
    loras_string = ''
    for key, value in prompt.items():
      # print(f"debug find_parameter_values: key={key} value={value}")
      if 'loras' in target_keys:
        # Match both formats: lora_xx and lora_name_x
        if re.match(r'lora(_name)?(_\d+)?', key):
          if value is not None:
            value = self.cleanup_fileName(value)
            loras_string += f'{value}, '
      
      # test if value is dict BEFORE cleaning up string value. come on, man...
      if isinstance(value, dict):
        self.find_parameter_values(target_keys, value, found_values)
      
      if key in target_keys:
        value = self.cleanup_fileName(value)
        found_values[key] = value
    
    if 'loras' in target_keys and loras_string:
      found_values['loras'] = loras_string.strip().strip(',')
    
    if len(target_keys) == 1:
      return found_values.get(target_keys[0], None)
    
    return found_values
  
  
  # String Type                 Example   isdecimal() isdigit() isnumeric()
  # --------------------------- --------- ----------- --------- -----------
  # Base 10 Numbers             '0123'    True        True      True
  # Fractions and Superscripts  '⅔','2²'  False       True      True
  # Roman Numerals              'ↁ'       False       False     True
  # --------------------------- --------- ----------- --------- -----------
  def generate_custom_name(self, keys_to_extract, prefix, delimiter, prompt, timestamp=datetime.now()):
    if '%' in prefix:
      custom_name = timestamp.strftime(prefix)
    else:
      custom_name = prefix
    
    if prompt is not None and keys_to_extract != ['']:
      found_values = {}
      # print(f"debug generate_custom_name: --prefix: {prefix}")
      # print(f"debug generate_custom_name: --keys_to_extract: {keys_to_extract}")
      # print(f"debug generate_custom_name: --prompt:")
      
      # now separating numbered keys from non-numbered keys:
      #   37.ckpt_name = i want the ckpt_name from node #37
      #      ckpt_name = i want the ckpt_name from the highest numbered node = the last one found
      # prompt looks like this:
      # {'1': {'class_type': 'KSampler',
      #   'inputs': {'cfg': 1.6, 
      #     'denoise': 1.0, ...
      for key in keys_to_extract:
        if not key: continue
        
        value = None
        node, nodeKey = None, None
        
        # check if this is a subfolder: starts with ./ or /, can also end with /
        # we also exclude datetime formats like "%A %d. %B %Y"
        if '/' in key and not '%' in key:
          # key is a subfolder: ./subfolder or ../subfolder or /subfolder
          value = key
        else:
          splitKey = key.split('.')
          # we also exclude cases like "..string" or "sting.string.x" etc
          # we also exclude datetime formats like "%A %d. %B %Y"
          if len(splitKey) == 2 and not '%' in key:
            # key has the form string.string
            if '' not in splitKey:
              # key has the form string.string
              if splitKey[0].isdecimal():
                # key has the form num.widget_name like 123.widget_name, we will then look for widget_name value in node #123
                node, nodeKey = splitKey[0], splitKey[1]
                if node in prompt:
                  # print(f"debug generate_custom_name: --node.nodeKey = {node}.{nodeKey}")
                  # splitKey[0] = #node number found in prompt, we will recurse only in that node:
                  self.find_keys_recursively(prompt[node], [nodeKey], found_values)
                else:
                  # if splitKey[0] = #num node not found in prompt; #num could have changed or user made a typo
                  print(f"SaveImageExtended info: node #{node} not found")
                  self.find_keys_recursively(prompt, [nodeKey], found_values)
              else:
                # key is in the form string.string = fixed string
                value = self.cleanup_fileName(key)
            else:
              # key is in the form ".string" or "string." or "." - we won't clean that up and keep as is, maybe it's a separator
              value = key
          else:
            # could be a datetime format
            if '%' in key:
              value = timestamp.strftime(key)
            # nodeKey is not a datetime, folder, has no dot, or multiple dots, could be a valid key to find, could be a fixed string - keep as is
            else:
              nodeKey = key
              self.find_keys_recursively(prompt, [nodeKey], found_values)
          # is key num.widget_name
        # is key subfolder
        
        # at this point we have a nodeKey, or a value, or both
        # print(f"debug generate_custom_name: ----key:   {nodeKey}")
        # print(f"debug generate_custom_name: ----value: {value}")
        if value is None:
          if nodeKey is not None:
            if nodeKey in found_values: value = found_values[nodeKey]
            if value is None:
              value = nodeKey
            else:
              value = self.cleanup_fileName(value)
        
        # at this point, value is not None anymore
        # now we analyze each value found and format them accordingly:
        # print(f"debug generate_custom_name: ----value: {value}")
        delim = delimiter
        
        # now we build the custom_name:
        if isinstance(value, str):
          # prefix and keys can very well be subfolders ending or starting with a /
          if custom_name.endswith('/'):
            # for subfolders, do not start filename with a delimiter...
            delim = ''
          else:
            # for subfolders in keys, do not clean the filename...
            if '/' in value and not value.endswith('/'):
              # print(f"debug generate_custom_name: ---------: folder")
              delim= ''
          # ".string" case
          if value.startswith('.'):
            delim = ''
        
        if isinstance(value, float):
          value = round(float(value), 1)
        
        custom_name += f"{delim}{value}"
        # print(f"debug generate_custom_name: ------custom_name: {custom_name}")
      # for each key
    return custom_name.strip(delimiter).strip('.').strip('/').strip(delimiter)
  
  
  def save_job_to_json(self, save_job_data, prompt, filename_prefix, positive_text_opt, negative_text_opt, job_custom_text, resolution, output_path, filename, timestamp=datetime.now()):
    prompt_keys_to_save = {}
    if 'basic' in save_job_data:
      if len(filename_prefix) > 0:
        prompt_keys_to_save['filename_prefix'] = filename_prefix
      prompt_keys_to_save['resolution'] = resolution
    if len(job_custom_text) > 0:
      prompt_keys_to_save['custom_text'] = job_custom_text
    
    if 'models' in save_job_data:
      models = self.find_parameter_values(['ckpt_name', 'loras', 'vae_name', 'model_name'], prompt)
      if models.get('ckpt_name'):
        prompt_keys_to_save['checkpoint'] = models['ckpt_name']
      if models.get('loras'):
        prompt_keys_to_save['loras'] = models['loras']
      if models.get('vae_name'):
        prompt_keys_to_save['vae'] = models['vae_name']
      if models.get('model_name'):
        prompt_keys_to_save['upscale_model'] = models['model_name']
    
    if 'sampler' in save_job_data:
      prompt_keys_to_save['sampler_parameters'] = self.find_parameter_values(['seed', 'steps', 'cfg', 'sampler_name', 'scheduler', 'denoise'], prompt)
    
    if 'prompt' in save_job_data:
      if positive_text_opt is not None:
        if not (isinstance(positive_text_opt, list) and
            len(positive_text_opt) == 2 and
            isinstance(positive_text_opt[0], str) and
            len(positive_text_opt[0]) < 6 and
            isinstance(positive_text_opt[1], (int, float))):
          prompt_keys_to_save['positive_prompt'] = positive_text_opt
      
      if negative_text_opt is not None:
        if not (isinstance(positive_text_opt, list) and len(negative_text_opt) == 2 and isinstance(negative_text_opt[0], str) and isinstance(negative_text_opt[1], (int, float))):
          prompt_keys_to_save['negative_prompt'] = negative_text_opt
      
      #If no user input for prompts
      if positive_text_opt is None and negative_text_opt is None:
        if prompt is not None:
          for key in prompt:
            class_type = prompt[key].get('class_type', None)
            inputs = prompt[key].get('inputs', {})
            
            # Efficiency Loaders prompt structure
            if class_type == 'Efficient Loader' or class_type == 'Eff. Loader SDXL':
              if 'positive' in inputs and 'negative' in inputs:
                prompt_keys_to_save['positive_prompt'] = inputs.get('positive')
                prompt_keys_to_save['negative_prompt'] = inputs.get('negative')
            
            # KSampler/UltimateSDUpscale prompt structure
            elif class_type == 'KSampler' or class_type == 'KSamplerAdvanced' or class_type == 'UltimateSDUpscale':
              positive_ref = inputs.get('positive', [])[0] if 'positive' in inputs else None
              negative_ref = inputs.get('negative', [])[0] if 'negative' in inputs else None
              
              positive_text = prompt.get(str(positive_ref), {}).get('inputs', {}).get('text', None)
              negative_text = prompt.get(str(negative_ref), {}).get('inputs', {}).get('text', None)
              
              # If we get non text inputs
              if positive_text is not None:
                if isinstance(positive_text, list):
                  if len(positive_text) == 2:
                    if isinstance(positive_text[0], str) and len(positive_text[0]) < 6:
                      if isinstance(positive_text[1], (int, float)):
                        continue
                prompt_keys_to_save['positive_prompt'] = positive_text
              
              if negative_text is not None:
                if isinstance(negative_text, list):
                  if len(negative_text) == 2:
                    if isinstance(negative_text[0], str) and len(negative_text[0]) < 6:
                      if isinstance(negative_text[1], (int, float)):
                        continue
                prompt_keys_to_save['negative_prompt'] = negative_text
    
    # Append data and save
    json_file_path = os.path.join(output_path, filename)
    existing_data = {}
    if os.path.exists(json_file_path):
      try:
        with open(json_file_path, 'r') as f:
          existing_data = json.load(f)
      except json.JSONDecodeError:
        print(f"SaveImageExtended {version} error: The file {json_file_path} is empty or malformed. Initializing with empty data.")
        existing_data = {}
    
    timestamp = timestamp.strftime('%c')
    new_entry = {}
    new_entry[timestamp] = prompt_keys_to_save
    existing_data.update(new_entry)
    
    with open(json_file_path, 'w') as f:
      json.dump(existing_data, f, indent=4)
  
  
  def get_metadata_png(self, img, prompt, extra_pnginfo=None):
    metadata = PngInfo()
    if prompt is not None:
      metadata.add_text('prompt', json.dumps(prompt))
    if extra_pnginfo is not None:
      for x in extra_pnginfo:
        metadata.add_text(x, json.dumps(extra_pnginfo[x]))
    
    return metadata
  
  
  def get_metadata_exif(self, img, prompt, extra_pnginfo=None):
    metadata = {}
    if prompt is not None:
      metadata["prompt"] = prompt
    if extra_pnginfo is not None:
      metadata.update(extra_pnginfo)
    
    ## For Comfy to load an image, it need a PNG tag at the root: Prompt={prompt}
    ## For AVIF WebP Jpeg, it's only Exif that's available... and UserComment is the best choice.

    ## This method gives good results, as long as you save the prompt/workflow in 2 separate Exif tags
    ## Otherwise, [ExifTool] will issue Warning: Invalid EXIF text encoding for UserComment
    #   entryOffset 10
    #   tag 37510
    #   type 2
    #   numValues 17699
    #   valueOffset 26
    ## Also when Comfy pnginfo.js reads it, all the quotes are escaped, making the prompt invalid
    ## exif type is PIL.Image.Exif
    exif = img.getexif()
    dump = json.dumps(metadata)
    # print(f"dump={dump}")   {"prompt": { .. }, "workflow": { .. }}
    # exif[ExifTags.Base.UserComment] = dump
    
    ## It seems better to separate the two
    # 0x010e: ImageDescription
    # 0x010f: Make
    # 0x9286: UserComment
    # both prompt and workflow must be in IFD close together of that can cause problems for the parseIFD function on import
    # https://exiftool.org/TagNames/EXIF.html
    # exif[0x9286] = "Prompt: " + json.dumps(metadata['prompt'])     # UserComment
    exif[0x010f] = "Prompt: " + json.dumps(metadata['prompt'])     # Make
    exif[0x010e] = "Workflow: " + json.dumps(metadata['workflow']) # ImageDescription
    
    # exif[ExifTags.Base.UserComment] = piexif.helper.UserComment.dump(json.dumps(metadata), encoding="unicode")  # type 4
    # exif[ExifTags.Base.UserComment] = piexif.helper.UserComment.dump(json.dumps(metadata), encoding="jis")      # type 1
    # exif[ExifTags.Base.UserComment] = piexif.helper.UserComment.dump(json.dumps(metadata), encoding="ascii")    # type 1
    exif_dat = exif.tobytes()
    
    # https://piexif.readthedocs.io/en/latest/functions.html#load

    # Both options exif_dict methods below result in type 4 data, read by parseExifData > parseIFD > readInt in pnginfo.js -> not processed
    #   entryOffset 10
    #   tag 34665
    #   type 4
    #   numValues 1
    #   valueOffset 26
    # Also, piexif.dump(exif_dict) already is a bytes object.
    # Also, 34665 if the correct tag for IFD according to https://pillow.readthedocs.io/en/stable/reference/ExifTags.html
    # from PIL.ExifTags import IFD
    # IFD.Exif.value -> 34665

    # https://stackoverflow.com/questions/61626067/python-add-arbitrary-exif-data-to-image-usercomment-field
    # exif_ifd = {piexif.ExifIFD.UserComment: json.dumps(metadata).encode()}
    # exif_dict = {"0th":{}, "Exif":exif_ifd, "GPS":{}, "1st":{}, "thumbnail":None}
    # exif_dat = piexif.dump(exif_dict)

    # https://stackoverflow.com/questions/8586940/writing-complex-custom-metadata-on-images-through-python
    # This seems like the right encoding, exiftool returns no error
    # exif_dict = {"0th":{}, "Exif":{}, "GPS":{}, "1st":{}, "thumbnail":None}
    # exif_dict["Exif"][piexif.ExifIFD.UserComment] = piexif.helper.UserComment.dump(json.dumps(metadata), encoding="unicode")
    # exif_dict["Exif"][piexif.ExifIFD.UserComment] = piexif.helper.UserComment.dump(json.dumps(metadata), encoding="ascii")
    # exif_dict["Exif"][piexif.ExifIFD.UserComment] = piexif.helper.UserComment.dump(json.dumps(metadata), encoding="jis")
    # exif_dat = piexif.dump(exif_dict)

    return exif_dat
  
  
  def save_image(self, image_path, img, prompt, save_metadata=save_metadata, extra_pnginfo=None, quality=75):
    # print(f"debug save_images: image_path={image_path}")
    output_ext = os.path.splitext(os.path.basename(image_path))[1]
    metadata = None
    kwargs = dict()
    
    # TODO: see if convert_hdr_to_8bit=False make a change
    
    # match is python 3.10+
    if output_ext in ['.avif']:
      if save_metadata: kwargs["exif"] = self.get_metadata_exif(img, prompt, extra_pnginfo)
      kwargs["quality"] = quality
      if quality == 100: kwargs["lossless"] = True
    elif output_ext in ['.webp']:
      if save_metadata: kwargs["exif"] = self.get_metadata_exif(img, prompt, extra_pnginfo)
      kwargs["quality"] = quality
      if quality == 100: kwargs["lossless"] = True
    elif output_ext in ['.jpg', '.jpeg']:
      if save_metadata: kwargs["exif"] = self.get_metadata_exif(img, prompt, extra_pnginfo)
      kwargs["quality"] = quality
      kwargs["optimize"] = self.optimize_image
    elif output_ext in ['.jxl']:
      if save_metadata: kwargs["exif"] = self.get_metadata_exif(img, prompt, extra_pnginfo)
      kwargs["quality"] = quality
      if quality == 100: kwargs["lossless"] = True
    elif output_ext in ['.tiff']:
      # tiff: i suspect no quality either
      kwargs["quality"] = quality
      kwargs["optimize"] = self.optimize_image
    elif output_ext in ['.png', '.gif']:
      # png/gif: no quality
      if save_metadata: kwargs["pnginfo"] = self.get_metadata_png(img, prompt, extra_pnginfo)
      kwargs["compress_level"] = self.png_compress_level
      kwargs["optimize"] = self.optimize_image
    # elif output_ext in ['.bmp']:
      # nothing to add
      
    # img.save(image_path, pnginfo=metadata, compress_level=self.png_compress_level)
    img.save(image_path, **kwargs)

# class SaveImageExtended -------------------------------------------------------------------------------


  # node will never return None values, except for optional input. Impossible.
  def save_images(self,
      images,
      filename_prefix,
      filename_keys,
      foldername_prefix,
      foldername_keys,
      delimiter,
      save_job_data,
      job_data_per_image,
      job_custom_text,
      save_metadata,
      counter_digits,
      counter_position,
      one_counter_per_folder,
      image_preview,
      output_ext,
      negative_text_opt=None,
      positive_text_opt=None,
      extra_pnginfo=None,
      prompt=None,
      quality=75,
    ):
    
    # print(f"filename_prefix = x{filename_prefix}x")
    # print(f"filename_keys = x{filename_keys}x")
    # print(f"foldername_prefix = x{foldername_prefix}x")
    # print(f"foldername_keys = x{foldername_keys}x")
    # print(f"delimiter = x{delimiter}x")
    # print(f"save_job_data = x{save_job_data}x")
    # print(f"job_data_per_image = x{job_data_per_image}x")
    # print(f"output_ext = x{output_ext}x")

    # apply default values: we replicate the default save image box
    if not filename_prefix and not filename_keys: filename_prefix=self.filename_prefix
    if delimiter: delimiter = delimiter[0]
    
    filename_keys_to_extract = [item.strip() for item in filename_keys.split(',')]
    foldername_keys_to_extract = [item.strip() for item in foldername_keys.split(',')]
    
    ################################## UNCOMMENT HERE TO SEE THE ENTIRE PROMPT
    # pprint.pprint(prompt)
    ##########################################################################
    timestamp = datetime.now()
    custom_filename = self.generate_custom_name(filename_keys_to_extract, filename_prefix, delimiter, prompt, timestamp)
    custom_foldername = self.generate_custom_name(foldername_keys_to_extract, foldername_prefix, delimiter, prompt, timestamp)
    
    # Get set resolution value
    i = 255. * images[0].cpu().numpy()
    img = Image.fromarray(np.clip(i, 0, 255).astype(np.uint8))
    resolution = f'{img.width}x{img.height}'
    
    # Create folders, count images, save images
    try:
      full_output_folder, filename, _, _, custom_filename = folder_paths.get_save_image_path(custom_filename, self.output_dir, images[0].shape[1], images[0].shape[0])
      output_path = os.path.join(full_output_folder, custom_foldername)
      # print(f"debug save_images: full_output_folder={full_output_folder}")
      # print(f"debug save_images: custom_foldername={custom_foldername}")
      # print(f"debug save_images: output_path={output_path}")
      os.makedirs(output_path, exist_ok=True)
      counter = self.get_latest_counter(one_counter_per_folder, output_path, filename, counter_digits, counter_position, output_ext)
      # print(f"debug save_images: counter for {output_ext}: {counter}")
    
      results = list()
      for image in images:
        i = 255. * image.cpu().numpy()
        img = Image.fromarray(np.clip(i, 0, 255).astype(np.uint8))
        
        if counter_position == 'last':
          file = f'{filename}{delimiter}{counter:0{counter_digits}}{output_ext}'
        else:
          file = f'{counter:0{counter_digits}}{delimiter}{filename}{output_ext}'
        
        image_path = os.path.join(output_path, file)
        self.save_image(image_path, img, prompt, save_metadata, extra_pnginfo, quality)
        
        if save_job_data != 'disabled' and job_data_per_image:
          self.save_job_to_json(save_job_data, prompt, filename_prefix, positive_text_opt, negative_text_opt, job_custom_text, resolution, output_path, f'{file.removesuffix(output_ext)}.json', timestamp)
        
        subfolder = self.get_subfolder_path(image_path, self.output_dir)
        results.append({ 'filename': file, 'subfolder': subfolder, 'type': self.type})
        counter += 1
      
      if save_job_data != 'disabled' and not job_data_per_image:
        self.save_job_to_json(save_job_data, prompt, filename_prefix, positive_text_opt, negative_text_opt, job_custom_text, resolution, output_path, 'jobs.json', timestamp)
    
    except OSError as e:
      print(f"SaveImageExtended {version} error: An error occurred while creating the subfolder or saving the image: {e}")
    else:
      if not image_preview:
        results = list()
      return { 'ui': { 'images': results } }


NODE_CLASS_MAPPINGS = {
  'SaveImageExtended': SaveImageExtended,
}


NODE_DISPLAY_NAME_MAPPINGS = {
  'SaveImageExtended': '💾 Save Image Extended',
}


# {'1': {'class_type': 'KSampler',
       # 'inputs': {'cfg': 1.6,
                  # 'denoise': 1.0,
                  # 'latent_image': ['6', 0],
                  # 'model': ['2', 0],
                  # 'negative': ['5', 0],
                  # 'positive': ['4', 0],
                  # 'sampler_name': 'lcm',
                  # 'scheduler': 'sgm_uniform',
                  # 'seed': 233248937945750,
                  # 'steps': 4}},
