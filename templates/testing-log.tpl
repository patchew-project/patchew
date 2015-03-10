% include('templates/header.tpl', title='Series')
% import urllib
% def uri(str):
%     return urllib.quote_plus(str)
% end

<ul class="nav nav-tabs">
    <li role="presentation"><a href="/series/{{uri(series['message-id'])}}">Thread</a></li>
    <li role="presentation" class="active"><a href="#">Testing</a></li>
</ul>
<br>


<h3>
    %if series.get('merged'):
        <span class="label label-primary">Merged</span>
    %elif series['testing-start-time']:
        <span class="label label-defulat">Testing</span>
    %elif series['testing-passed']:
        %if series['testing-has-warning']:
        <span class="label label-warning">Warning</span>
        %else:
        <span class="label label-success">Passed</span>
        %end
    %elif series['testing-passed'] == False:
        <span class="label label-danger">Failed</span>
    %else:
        <span class="label label-default">Not started</span>
    %end
</h3>
<br>
%if log:
    <pre>{{log}}</pre>
%end

% include('templates/footer.tpl')
